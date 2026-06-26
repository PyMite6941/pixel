"""Pixel AI — license issuance service (mirrors finance-kit auth-service).

Endpoints:
  POST /issue        — Admin: issue a license key (requires X-Issue-Secret)
  POST /redeem       — Public: redeem USDC payment for license key
  POST /validate     — Public: validate a license JWT

Usage:
  from service.license_server import add_license_routes
  add_license_routes(app)
"""

import hmac
import logging
import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

import resend
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from google.api_core.exceptions import AlreadyExists, GoogleAPIError
from google.cloud import firestore

from service.auth_jwt import (
    create_license_jwt, verify_license_jwt,
    TIER_FEATURES, TIER_EXPIRY_DAYS, TIER_IP_LIMITS,
)
from service.onchain import verify_usdc_payment

log = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")

ISSUE_SECRET = os.getenv("PIXEL_ISSUE_SECRET", "")
EMAIL_FROM = os.getenv("PIXEL_EMAIL_FROM", "Pixel AI <licenses@resend.dev>")
EMAIL_PROVIDER = os.getenv("PIXEL_EMAIL_PROVIDER", "resend").lower()
SMTP_HOST = os.getenv("PIXEL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("PIXEL_SMTP_PORT", "587"))
SMTP_USER = os.getenv("PIXEL_SMTP_USER", "")
SMTP_PASS = os.getenv("PIXEL_SMTP_PASS", "")

# Price per tier in USDC
TIER_PRICE_USDC = {"pro": 29, "enterprise": 99}

# Where to store keys (file-based fallback if Firestore unavailable)
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_db: Optional[firestore.Client] = None


def _firestore():
    global _db
    if _db is None:
        try:
            _db = firestore.Client()
        except Exception:
            log.warning("Firestore unavailable; using file-based fallback")
            return None
    return _db


def _valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email)) and len(email) <= 254


def _safe_doc_id(order_id: str) -> str:
    return order_id.replace("/", "_")[:1500]


def _record_license(order_id: str, email: str, tier: str, token: str, claims: dict) -> dict:
    """Record a license issuance. Firestore first, fallback to JSON file."""
    record = {
        "email": email,
        "order_id": order_id,
        "tier": tier,
        "jti": claims.get("jti"),
        "max_ips": claims.get("max_ips"),
        "features": claims.get("features", []),
        "token": token,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }

    db = _firestore()
    if db is not None:
        doc_ref = db.collection("pixel_licenses").document(_safe_doc_id(order_id))
        try:
            doc_ref.create(record)
        except AlreadyExists:
            raise HTTPException(status_code=409,
                                detail="A license has already been issued for this payment.")
        except GoogleAPIError as exc:
            raise HTTPException(status_code=503, detail=f"License store unavailable: {exc}")
    else:
        file_path = DATA_DIR / "licenses.json"
        licenses = []
        if file_path.exists():
            try:
                import json
                licenses = json.loads(file_path.read_text())
            except Exception:
                pass
        for lic in licenses:
            if lic.get("order_id") == order_id:
                raise HTTPException(status_code=409,
                                    detail="A license has already been issued for this payment.")
        licenses.append(record)
        file_path.write_text(__import__('json').dumps(licenses, indent=2))

    return record


def _issue_license(email: str, tier: str, order_id: str) -> dict:
    """Mint + record + optionally email a license. Idempotent on order_id."""
    token = create_license_jwt(email, tier=tier)
    claims = verify_license_jwt(token) or {}

    record = _record_license(order_id, email, tier, token, claims)
    sent = _send_license_email(email, token, tier)

    return {"token": token, "email": email, "tier": tier, "email_sent": sent}


def _license_html(token: str, tier_label: str) -> str:
    return f"""
<p>Thanks for subscribing to Pixel AI {tier_label}!</p>
<p><strong>Your API key:</strong></p>
<pre style="background:#111;padding:16px;border-radius:8px;font-size:13px;word-break:break-all">{token}</pre>
<p>Use it with the <code>X-API-Key</code> header to call the Pixel AI API.</p>
<p style="color:#888;font-size:12px">Key expires in {TIER_EXPIRY_DAYS.get(tier.lower(), 31)} days. Renew by placing a new order.</p>
"""


def _send_license_email(to_email: str, token: str, tier: str) -> bool:
    tier_label = "Enterprise" if tier == "enterprise" else "Pro"
    subject = f"Your Pixel AI {tier_label} License Key"
    html = _license_html(token, tier_label)
    text = (f"Your Pixel AI {tier_label} license key:\n\n{token}\n\n"
            f"Use it with the X-API-Key header to call the API.")
    try:
        if EMAIL_PROVIDER == "smtp":
            if not (SMTP_USER and SMTP_PASS):
                log.warning(f"SMTP not configured; key for {to_email}:\n{token}")
                return False
            msg = EmailMessage()
            msg["From"] = f"Pixel AI <{SMTP_USER}>"
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.set_content(text)
            msg.add_alternative(html, subtype="html")
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
            return True

        if not resend.api_key:
            log.warning(f"Resend not configured; key for {to_email}:\n{token}")
            return False
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": to_email,
            "subject": subject,
            "html": html,
        })
        return True
    except Exception as exc:
        log.warning(f"Email send failed for {to_email}: {exc}")
        return False


def add_license_routes(app):
    """Register license endpoints on a FastAPI app."""

    @app.get("/api/license/health")
    async def license_health():
        return {"status": "ok"}

    @app.post("/api/license/issue")
    async def license_issue(request: Request):
        """Issue a license key. Requires X-Issue-Secret header."""
        if ISSUE_SECRET and not hmac.compare_digest(
            request.headers.get("X-Issue-Secret", "").encode(), ISSUE_SECRET.encode()
        ):
            raise HTTPException(status_code=401, detail="Invalid or missing X-Issue-Secret header")

        body = await request.json()
        email = (body.get("email") or "").strip().lower()
        tier = (body.get("tier") or "pro").strip().lower()
        order_id = (body.get("order_id") or "").strip()

        if not _valid_email(email):
            raise HTTPException(status_code=400, detail="Valid email required")
        if tier not in TIER_FEATURES:
            raise HTTPException(status_code=400, detail=f"tier must be one of: {', '.join(TIER_FEATURES.keys())}")
        if not order_id:
            raise HTTPException(status_code=400, detail="order_id required")

        return _issue_license(email, tier, order_id)

    @app.post("/api/license/redeem")
    async def license_redeem(request: Request):
        """Public: submit a Base tx hash + email + tier. We verify on-chain, then issue."""
        body = await request.json()
        email = (body.get("email") or "").strip().lower()
        tier = (body.get("tier") or "pro").strip().lower()
        tx_hash = (body.get("tx_hash") or "").strip().lower()

        if not _valid_email(email):
            raise HTTPException(status_code=400, detail="Valid email required")
        if tier not in TIER_PRICE_USDC:
            raise HTTPException(status_code=400, detail=f"tier must be one of: {', '.join(TIER_PRICE_USDC.keys())}")
        if not (tx_hash.startswith("0x") and len(tx_hash) == 66):
            raise HTTPException(status_code=400, detail="Valid transaction hash required")

        ok, reason, _amount = verify_usdc_payment(tx_hash, TIER_PRICE_USDC[tier])
        if not ok:
            raise HTTPException(status_code=402, detail=reason)

        return _issue_license(email, tier, tx_hash)

    @app.post("/api/license/validate")
    async def license_validate(request: Request):
        """Public: validate a license JWT."""
        body = await request.json()
        token = body.get("token", "")
        claims = verify_license_jwt(token)
        if not claims:
            raise HTTPException(status_code=401, detail="Invalid or expired license key")
        return {
            "valid": True,
            "email": claims["sub"],
            "tier": claims["tier"],
            "features": claims["features"],
        }

    return app
