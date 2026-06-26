import json
import time
import secrets
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

_USERS_FILE = DATA_DIR / "users.json"
_API_KEYS_FILE = DATA_DIR / "api_keys.json"
_USAGE_FILE = DATA_DIR / "usage.json"


@dataclass
class User:
    user_id: str
    name: str
    email: str
    tier: str = "free"      # free, pro, enterprise
    created_at: float = 0.0
    active: bool = True


@dataclass
class APIKey:
    key: str
    user_id: str
    name: str = "default"
    created_at: float = 0.0
    active: bool = True


@dataclass
class UsageRecord:
    user_id: str
    api_key: str
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    cost: float = 0.0
    period_start: float = 0.0
    period_end: float = 0.0


TIER_LIMITS = {
    "free": {
        "requests_per_day": 100,
        "tokens_per_month": 1_000_000,
        "max_context": 4096,
        "cost_per_1k_tokens": 0.002,
        "providers": ["ollama", "groq"],
        "concurrent_requests": 1,
    },
    "pro": {
        "requests_per_day": 10_000,
        "tokens_per_month": 10_000_000,
        "max_context": 32768,
        "cost_per_1k_tokens": 0.001,
        "providers": ["ollama", "groq", "gemini", "claude"],
        "concurrent_requests": 5,
    },
    "enterprise": {
        "requests_per_day": 100_000,
        "tokens_per_month": 100_000_000,
        "max_context": 131072,
        "cost_per_1k_tokens": 0.0005,
        "providers": ["ollama", "groq", "gemini", "claude", "local_model"],
        "concurrent_requests": 50,
    },
}


class AuthManager:
    def __init__(self):
        self._users: dict[str, User] = {}
        self._api_keys: dict[str, APIKey] = {}
        self._load()

    def _load(self):
        if _USERS_FILE.exists():
            try:
                data = json.loads(_USERS_FILE.read_text())
                for item in data:
                    u = User(**item)
                    self._users[u.user_id] = u
            except Exception:
                pass
        if _API_KEYS_FILE.exists():
            try:
                data = json.loads(_API_KEYS_FILE.read_text())
                for item in data:
                    k = APIKey(**item)
                    self._api_keys[k.key] = k
            except Exception:
                pass

    def _save_users(self):
        _USERS_FILE.write_text(json.dumps([asdict(u) for u in self._users.values()], indent=2))

    def _save_keys(self):
        _API_KEYS_FILE.write_text(json.dumps([asdict(k) for k in self._api_keys.values()], indent=2))

    def create_user(self, name: str, email: str, tier: str = "free") -> User:
        user_id = f"usr_{secrets.token_hex(8)}"
        user = User(user_id=user_id, name=name, email=email, tier=tier, created_at=time.time())
        self._users[user_id] = user
        self._save_users()
        return user

    def create_api_key(self, user_id: str, name: str = "default") -> APIKey:
        key = f"px_{secrets.token_hex(24)}"
        api_key = APIKey(key=key, user_id=user_id, name=name, created_at=time.time())
        self._api_keys[key] = api_key
        self._save_keys()
        return api_key

    def validate_key(self, key: str) -> Optional[User]:
        api_key = self._api_keys.get(key)
        if not api_key or not api_key.active:
            return None
        user = self._users.get(api_key.user_id)
        if not user or not user.active:
            return None
        return user

    def get_user_by_key(self, key: str) -> Optional[User]:
        return self.validate_key(key)

    def get_tier(self, user: User) -> dict:
        return TIER_LIMITS.get(user.tier, TIER_LIMITS["free"])

    def list_users(self) -> list[User]:
        return list(self._users.values())

    def list_keys(self) -> list[APIKey]:
        return list(self._api_keys.values())

    def revoke_key(self, key: str) -> bool:
        if key in self._api_keys:
            self._api_keys[key].active = False
            self._save_keys()
            return True
        return False


class UsageTracker:
    def __init__(self):
        self._usage: dict[str, list[UsageRecord]] = {}
        self._load()

    def _load(self):
        if _USAGE_FILE.exists():
            try:
                data = json.loads(_USAGE_FILE.read_text())
                for user_id, records in data.items():
                    self._usage[user_id] = [UsageRecord(**r) for r in records]
            except Exception:
                pass

    def _save(self):
        data = {}
        for user_id, records in self._usage.items():
            data[user_id] = [asdict(r) for r in records]
        _USAGE_FILE.write_text(json.dumps(data, indent=2))

    def track(self, user_id: str, api_key: str, input_tokens: int = 0,
              output_tokens: int = 0, cost: float = 0.0):
        now = time.time()
        today_start = now - (now % 86400)
        month_start = now - (now % (86400 * 30))

        records = self._usage.setdefault(user_id, [])
        current = None
        for r in records:
            if r.period_start >= month_start and r.api_key == api_key:
                current = r
                break

        if not current:
            current = UsageRecord(
                user_id=user_id, api_key=api_key,
                period_start=month_start, period_end=month_start + (86400 * 30),
            )
            records.append(current)

        current.input_tokens += input_tokens
        current.output_tokens += output_tokens
        current.requests += 1
        current.cost += cost
        self._save()

    def get_usage(self, user_id: str) -> Optional[UsageRecord]:
        records = self._usage.get(user_id, [])
        if not records:
            return None
        merged = UsageRecord(user_id=user_id, api_key="")
        for r in records:
            merged.input_tokens += r.input_tokens
            merged.output_tokens += r.output_tokens
            merged.requests += r.requests
            merged.cost += r.cost
        return merged

    def check_limits(self, user: User) -> dict:
        tier = TIER_LIMITS.get(user.tier, TIER_LIMITS["free"])
        usage = self.get_usage(user.user_id)
        if not usage:
            return {"within_limits": True, "requests_used": 0, "tokens_used": 0}

        total_tokens = usage.input_tokens + usage.output_tokens
        return {
            "within_limits": total_tokens < tier["tokens_per_month"],
            "requests_used": usage.requests,
            "tokens_used": total_tokens,
            "requests_limit": tier["requests_per_day"],
            "tokens_limit": tier["tokens_per_month"],
        }
