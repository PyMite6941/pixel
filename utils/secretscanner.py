import re
import json
from pathlib import Path

_SECRETS_FILE = Path(__file__).parent.parent / "memory" / "secrets_ref.json"

_PATTERNS = [
    ("API Key (generic)", re.compile(r'(?i)(?:api[_-]?key|apikey)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{16,64})["\']?')),
    ("Bearer Token", re.compile(r'(?i)bearer\s+([a-zA-Z0-9_\-\.]{20,})')),
    ("JWT Token", re.compile(r'eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}')),
    ("GitHub Token", re.compile(r'(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,}')),
    ("AWS Access Key", re.compile(r'(?i)aws[_-]?access[_-]?key[_-]?id\s*[:=]\s*["\']?([A-Z0-9]{16,20})["\']?')),
    ("AWS Secret Key", re.compile(r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*["\']?([a-zA-Z0-9\/+]{40})["\']?')),
    ("Generic Secret", re.compile(r'(?i)(?:secret|password|token|private[_-]?key)\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.\/+]{16,})["\']?')),
    ("SSH Private Key", re.compile(r'-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----')),
    ("Slack Token", re.compile(r'xox[baprs]-[a-zA-Z0-9]{10,}')),
    ("Google API Key", re.compile(r'(?i)AIza[0-9A-Za-z\-_]{35}')),
    ("Heroku API Key", re.compile(r'(?i)heroku[_-]?api[_-]?key\s*[:=]\s*["\']?([a-zA-Z0-9\-]{20,})["\']?')),
    ("Discord Token", re.compile(r'(?:mfa\.|[a-z]{24}\.[a-z]{6}\.)[a-zA-Z0-9_\-]{27,}')),
    ("Slack Webhook", re.compile(r'https://hooks\.slack\.com/services/[a-zA-Z0-9/]{20,}')),
    ("Generic Private Key", re.compile(r'-----BEGIN\s+PRIVATE\s+KEY-----')),
    ("npm Token", re.compile(r'(?i)npm[_-]?token\s*[:=]\s*["\']?([a-zA-Z0-9\-]{20,})["\']?')),
]


class SecretMatch:
    def __init__(self, name: str, pattern: re.Pattern, full_match: str):
        self.name = name
        self.pattern = pattern
        self.full_match = full_match


def scan(text: str) -> list[SecretMatch]:
    found: list[SecretMatch] = []
    for name, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            found.append(SecretMatch(name, pattern, match.group(0)))
    return found


def redact(text: str, replacement: str = "<redacted>") -> str:
    result = text
    for _, pattern in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def has_secrets(text: str) -> bool:
    for _, pattern in _PATTERNS:
        if pattern.search(text):
            return True
    return False


def save_secrets_ref(secrets: list[SecretMatch], source: str = "user_input") -> str:
    _SECRETS_FILE.parent.mkdir(exist_ok=True)
    refs = []
    for i, s in enumerate(secrets):
        refs.append({
            "ref": f"secret_{i}",
            "type": s.name,
            "source": source,
            "preview": s.full_match[:20] + "..." if len(s.full_match) > 20 else s.full_match,
        })
    data = {"secrets": refs}
    _SECRETS_FILE.write_text(json.dumps(data, indent=2))
    return str(_SECRETS_FILE)


def load_secrets_ref() -> dict:
    if _SECRETS_FILE.exists():
        return json.loads(_SECRETS_FILE.read_text())
    return {"secrets": []}
