import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_PREFS_FILE = Path(__file__).parent / "memory" / "prefs.json"


def _load_prefs() -> dict:
    if _PREFS_FILE.exists():
        with open(_PREFS_FILE) as f:
            return json.load(f)
    return {}


def save_prefs(updates: dict) -> None:
    prefs = _load_prefs()
    prefs.update(updates)
    _PREFS_FILE.parent.mkdir(exist_ok=True)
    with open(_PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)


_prefs = _load_prefs()


class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

    FAST_MODEL = "llama-3.1-8b-instant"
    SMART_MODEL = "llama-3.3-70b-versatile"
    CLAUDE_MODEL = "claude-sonnet-4-6"
    GEMINI_MODEL = "gemini-1.5-flash"

    # User preferences — edit memory/prefs.json or use /set command at runtime
    PREFERRED_PROVIDER: str = _prefs.get("preferred_provider", "groq")   # groq | gemini | claude
    VERBOSITY: str = _prefs.get("verbosity", "normal")                    # quiet | normal | verbose
    MAX_HISTORY: int = _prefs.get("max_history", 20)
    SMART_MODE: bool = _prefs.get("smart_mode", False)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
