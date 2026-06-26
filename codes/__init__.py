import json
import secrets
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


CODES_DIR = Path(__file__).parent / "data"
CODES_DIR.mkdir(exist_ok=True)

_CODES_FILE = CODES_DIR / "trial_codes.json"
_REDEMPTIONS_FILE = CODES_DIR / "redemptions.json"
_WEBSITE_KEYS_FILE = CODES_DIR / "website_keys.json"

TRIAL_DURATION_DAYS = 30
TRIAL_TIER = "pro"


@dataclass
class TrialCode:
    code: str
    created_by: str = ""          # website key name or "admin"
    tier: str = TRIAL_TIER
    max_uses: int = 1
    uses: int = 0
    created_at: float = 0.0
    expires_at: float = 0.0
    active: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class Redemption:
    code: str
    user_id: str
    api_key: str
    redeemed_at: float = 0.0
    expires_at: float = 0.0


@dataclass
class WebsiteKey:
    name: str
    key: str
    active: bool = True
    created_at: float = 0.0


class TrialCodeManager:
    """Manages 30-day trial codes for the AIaaS — websites can generate codes programmatically."""

    def __init__(self):
        self._codes: dict[str, TrialCode] = {}
        self._redemptions: list[Redemption] = []
        self._website_keys: dict[str, WebsiteKey] = {}
        self._load()

    def _load(self):
        for path, container, cls in [
            (_CODES_FILE, self._codes, TrialCode),
            (_REDEMPTIONS_FILE, self._redemptions, Redemption),
            (_WEBSITE_KEYS_FILE, self._website_keys, WebsiteKey),
        ]:
            if path.exists():
                try:
                    data = json.loads(path.read_text())
                    if isinstance(data, list):
                        container.extend(cls(**item) for item in data)
                    elif isinstance(data, dict):
                        for k, v in data.items():
                            container[k] = cls(**v) if isinstance(v, dict) else v
                except Exception:
                    pass

    def _save(self):
        _CODES_FILE.write_text(json.dumps(
            {k: asdict(v) for k, v in self._codes.items()}, indent=2))
        _REDEMPTIONS_FILE.write_text(json.dumps(
            [asdict(r) for r in self._redemptions], indent=2))
        _WEBSITE_KEYS_FILE.write_text(json.dumps(
            {k: asdict(v) for k, v in self._website_keys.items()}, indent=2))

    # --- Code Generation ---

    def generate_code(self, created_by: str = "admin", tier: str = TRIAL_TIER,
                      max_uses: int = 1, days_valid: int = TRIAL_DURATION_DAYS,
                      metadata: dict = None) -> TrialCode:
        code_str = self._make_code()
        now = time.time()
        code = TrialCode(
            code=code_str,
            created_by=created_by,
            tier=tier,
            max_uses=max_uses,
            created_at=now,
            expires_at=now + (days_valid * 86400),
            metadata=metadata or {},
        )
        self._codes[code_str] = code
        self._save()
        return code

    def _make_code(self) -> str:
        part1 = secrets.token_hex(3).upper()[:5]
        part2 = secrets.token_hex(3).upper()[:5]
        return f"PX-{part1}-{part2}"

    def generate_batch(self, count: int, created_by: str = "admin",
                       tier: str = TRIAL_TIER, days_valid: int = TRIAL_DURATION_DAYS) -> list[TrialCode]:
        codes = []
        for _ in range(count):
            code = self.generate_code(created_by, tier, 1, days_valid)
            codes.append(code)
        return codes

    # --- Validation & Redemption ---

    def validate_code(self, code_str: str) -> dict:
        code = self._codes.get(code_str.upper())
        if not code:
            return {"valid": False, "reason": "Code not found"}
        if not code.active:
            return {"valid": False, "reason": "Code has been deactivated"}
        if code.uses >= code.max_uses:
            return {"valid": False, "reason": "Code has been fully used"}
        if time.time() > code.expires_at:
            return {"valid": False, "reason": "Code has expired"}
        return {
            "valid": True,
            "tier": code.tier,
            "days_remaining": int((code.expires_at - time.time()) / 86400),
        }

    def redeem_code(self, code_str: str, user_id: str, api_key: str) -> dict:
        validation = self.validate_code(code_str)
        if not validation["valid"]:
            return {"success": False, "reason": validation["reason"]}

        code = self._codes[code_str.upper()]
        code.uses += 1

        now = time.time()
        redemption = Redemption(
            code=code_str.upper(),
            user_id=user_id,
            api_key=api_key,
            redeemed_at=now,
            expires_at=now + (TRIAL_DURATION_DAYS * 86400),
        )
        self._redemptions.append(redemption)
        self._save()

        return {
            "success": True,
            "tier": code.tier,
            "expires_at": redemption.expires_at,
            "days": TRIAL_DURATION_DAYS,
        }

    # --- Website API Key Management ---

    def create_website_key(self, name: str) -> WebsiteKey:
        key = f"ws_{secrets.token_hex(16)}"
        wk = WebsiteKey(name=name, key=key, created_at=time.time())
        self._website_keys[name] = wk
        self._save()
        return wk

    def validate_website_key(self, key: str) -> Optional[WebsiteKey]:
        for wk in self._website_keys.values():
            if wk.key == key and wk.active:
                return wk
        return None

    def revoke_website_key(self, name: str) -> bool:
        wk = self._website_keys.get(name)
        if wk:
            wk.active = False
            self._save()
            return True
        return False

    # --- Admin ---

    def list_codes(self, include_expired: bool = False) -> list[dict]:
        results = []
        for code in self._codes.values():
            if not include_expired and time.time() > code.expires_at:
                continue
            results.append(asdict(code))
        return sorted(results, key=lambda x: x.get("created_at", 0), reverse=True)

    def list_redemptions(self) -> list[dict]:
        return [asdict(r) for r in sorted(self._redemptions, key=lambda x: x.redeemed_at, reverse=True)]

    def deactivate_code(self, code_str: str) -> bool:
        code = self._codes.get(code_str.upper())
        if code:
            code.active = False
            self._save()
            return True
        return False

    def get_stats(self) -> dict:
        total = len(self._codes)
        active = sum(1 for c in self._codes.values() if c.active and c.uses < c.max_uses and time.time() <= c.expires_at)
        redeemed = len(self._redemptions)
        expired = sum(1 for c in self._codes.values() if time.time() > c.expires_at)
        return {
            "total_codes": total,
            "active_codes": active,
            "redeemed": redeemed,
            "expired": expired,
            "trial_days": TRIAL_DURATION_DAYS,
            "trial_tier": TRIAL_TIER,
        }
