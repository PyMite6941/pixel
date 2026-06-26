from utils.secretscanner import scan, redact, has_secrets


class TestSecretScanner:
    def test_scan_finds_api_key(self):
        text = "my api_key = sk-1234567890abcdef1234567890abcdef"
        results = scan(text)
        assert len(results) > 0

    def test_scan_finds_bearer_token(self):
        text = "Authorization: bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dkjf43jkl5"
        results = scan(text)
        assert len(results) > 0

    def test_scan_returns_empty_for_safe_text(self):
        text = "hello world this is safe text without secrets"
        results = scan(text)
        assert len(results) == 0

    def test_redact_replaces_secrets(self):
        text = "my api_key = sk-1234567890abcdef1234567890abcdef"
        result = redact(text)
        assert result != text
        assert "<redacted>" in result

    def test_has_secrets_true(self):
        assert has_secrets("api_key = sk-1234567890abcdef1234567890abcdef")

    def test_has_secrets_false(self):
        assert not has_secrets("hello world")

    def test_scan_finds_jwt(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dkjf43jkl5fjdksl"
        text = f"token = {jwt}"
        results = scan(text)
        assert len(results) > 0
        names = [r.name for r in results]
        assert "JWT Token" in names or "Generic Secret" in names
