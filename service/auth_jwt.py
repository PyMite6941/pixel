"""Pixel AI — JWT license keys (mirrors finance-kit auth-service pattern).

License keys are signed JWTs with embedded tier, features, jti, and max_ips.
They serve as the primary API key — no separate key store needed.

Usage:
  from service.auth_jwt import create_license_jwt, verify_license_jwt, get_ip_limits
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError

log = logging.getLogger(__name__)

SECRET_KEY = os.getenv("PIXEL_JWT_SECRET", "")
if not SECRET_KEY:
    import secrets
    SECRET_KEY = secrets.token_hex(64)
    log.warning("PIXEL_JWT_SECRET not set. Generated ephemeral key. Set it before deploying.")

ALGORITHM = "HS256"

TIER_FEATURES = {
    "free": [
        "api:ask",
    ],
    "pro": [
        "api:ask",
        "api:stream",
        "api:engine",
        "api:compose",
        "api:training",
    ],
    "enterprise": [
        "api:ask",
        "api:stream",
        "api:engine",
        "api:compose",
        "api:training",
        "api:evals",
        "api:admin",
    ],
}

TIER_EXPIRY_DAYS = {
    "free": 0,
    "pro": 31,
    "enterprise": 31,
}

TIER_IP_LIMITS = {
    "free": 1,
    "pro": 5,
    "enterprise": 50,
}


def create_license_jwt(email_or_id: str, tier: str = "pro", ttl_days: Optional[int] = None) -> str:
    tier = tier.lower()
    if tier not in TIER_FEATURES:
        raise ValueError(f"Unknown tier: {tier}")
    now = datetime.now(timezone.utc)
    ttl = ttl_days if ttl_days is not None else TIER_EXPIRY_DAYS.get(tier, 31)
    payload = {
        "sub": email_or_id,
        "features": TIER_FEATURES[tier],
        "tier": tier,
        "jti": uuid.uuid4().hex,
        "max_ips": TIER_IP_LIMITS[tier],
        "iat": now,
    }
    if ttl > 0:
        payload["exp"] = now + timedelta(days=ttl)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_license_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_ip_limits(tier: str) -> int:
    return TIER_IP_LIMITS.get(tier, 1)


def get_expiry_days(tier: str) -> int:
    return TIER_EXPIRY_DAYS.get(tier, 31)
