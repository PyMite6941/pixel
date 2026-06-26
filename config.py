import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_PREFS_FILE = Path(__file__).parent / "memory" / "prefs.json"
_SECRETS_FILE = Path(__file__).parent / "secrets.toml"
_SECRETS_EXAMPLE = Path(__file__).parent / "secrets.toml.example"


def _load_toml() -> dict:
    if not _SECRETS_FILE.exists():
        return {}

    try:
        import tomllib
        with open(_SECRETS_FILE, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        pass

    try:
        import tomli
        with open(_SECRETS_FILE, "rb") as f:
            return tomli.load(f)
    except ImportError:
        pass

    result = {}
    with open(_SECRETS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            result[key] = val
    return result


def _load_prefs() -> dict:
    if _PREFS_FILE.exists():
        try:
            with open(_PREFS_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_prefs(updates: dict) -> None:
    prefs = _load_prefs()
    prefs.update(updates)
    _PREFS_FILE.parent.mkdir(exist_ok=True)
    with open(_PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)


_SECRETS = _load_toml()
_prefs = _load_prefs()

_RATE_LIMIT_STATE: dict[str, dict] = {}


def get_rate_limit_state() -> dict[str, dict]:
    now = time.time()
    for p, s in _RATE_LIMIT_STATE.items():
        cooldown = s.get("cooldown_until", 0)
        if cooldown > 0 and cooldown < now:
            s["rate_limited"] = False
            s["cooldown_until"] = 0
    return dict(_RATE_LIMIT_STATE)


def mark_rate_limited(provider: str, cooldown_seconds: int | None = None) -> None:
    if cooldown_seconds is None:
        cooldown_seconds = _prefs.get("rate_limit_cooldown", 60)
    _RATE_LIMIT_STATE[provider] = {
        "rate_limited": True,
        "cooldown_until": time.time() + cooldown_seconds,
        "limited_at": time.time(),
    }


def mark_provider_ok(provider: str) -> None:
    if provider in _RATE_LIMIT_STATE:
        _RATE_LIMIT_STATE[provider]["rate_limited"] = False
        _RATE_LIMIT_STATE[provider]["cooldown_until"] = 0


def update_rate_limits_from_headers(provider: str, headers: dict) -> dict:
    state = _RATE_LIMIT_STATE.setdefault(provider, {
        "rate_limited": False,
        "cooldown_until": 0,
        "remaining": None,
        "limit": None,
        "reset_at": None,
    })

    for key, val in headers.items():
        lower = key.lower().replace("-", "").replace("_", "")
        if "xratelimitremaining" in lower:
            state["remaining"] = int(val)
        elif "xratelimitlimit" in lower:
            state["limit"] = int(val)
        elif "xratelimitreset" in lower:
            try:
                state["reset_at"] = float(val) if "." in val else int(val)
            except ValueError:
                state["reset_at"] = val

    return state


def get_provider_usage_state() -> dict:
    state = get_rate_limit_state()
    return {
        p: {
            "rate_limited": s.get("rate_limited", False),
            "cooldown_remaining": max(0, int(s.get("cooldown_until", 0) - time.time())),
            "remaining": s.get("remaining"),
            "limit": s.get("limit"),
        }
        for p, s in state.items()
    }


def _get_secret(key: str, default: str | None = None) -> str | None:
    val = _SECRETS.get(key) or os.getenv(key)
    if val is not None:
        val = str(val).strip()
        if val and val != "YOUR_KEY_HERE" and not val.startswith("gsk_") and "your_key" not in val.lower():
            return val
    return default


class Config:
    GROQ_API_KEY = _get_secret("GROQ_API_KEY")
    ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = _get_secret("GOOGLE_API_KEY")

    # Groq deprecated llama-3.1-8b-instant and llama-3.3-70b-versatile (announced 2026-06-17).
    # Default to the GA gpt-oss models; override via env/secrets if needed.
    FAST_MODEL = os.getenv("FAST_MODEL") or _SECRETS.get("FAST_MODEL", "openai/gpt-oss-20b")
    SMART_MODEL = os.getenv("SMART_MODEL") or _SECRETS.get("SMART_MODEL", "openai/gpt-oss-120b")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL") or _SECRETS.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL") or _SECRETS.get("GEMINI_MODEL", "gemini-2.0-flash")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or _SECRETS.get("OLLAMA_MODEL", "llama3.2")

    _has_cloud = bool(GROQ_API_KEY or ANTHROPIC_API_KEY or GOOGLE_API_KEY)
    PREFERRED_PROVIDER: str = (
        _prefs.get("preferred_provider")
        or _SECRETS.get("PREFERRED_PROVIDER")
        or ("ollama" if not _has_cloud else "groq")
    )
    VERBOSITY: str = _prefs.get("verbosity", "normal")
    MAX_HISTORY: int = int(_prefs.get("max_history", 20))
    SMART_MODE: bool = _prefs.get("smart_mode", False)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    RATE_LIMIT_COOLDOWN: int = int(_prefs.get("rate_limit_cooldown", 60))
