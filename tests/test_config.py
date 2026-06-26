import os
from config import Config, get_rate_limit_state, mark_rate_limited, mark_provider_ok


class TestConfig:
    def test_config_has_expected_attributes(self):
        assert hasattr(Config, "GROQ_API_KEY")
        assert hasattr(Config, "ANTHROPIC_API_KEY")
        assert hasattr(Config, "GOOGLE_API_KEY")
        assert hasattr(Config, "FAST_MODEL")
        assert hasattr(Config, "SMART_MODEL")
        assert hasattr(Config, "PREFERRED_PROVIDER")
        assert hasattr(Config, "MAX_HISTORY")
        assert hasattr(Config, "SMART_MODE")
        assert hasattr(Config, "RATE_LIMIT_COOLDOWN")

    def test_default_models(self):
        assert Config.FAST_MODEL == "openai/gpt-oss-20b"
        assert Config.SMART_MODEL == "openai/gpt-oss-120b"

    def test_default_preferences(self):
        assert Config.PREFERRED_PROVIDER in ("groq", "ollama", "gemini", "claude")
        assert Config.MAX_HISTORY > 0


class TestRateLimitState:
    def setup_method(self):
        mark_provider_ok("groq")
        mark_provider_ok("gemini")

    def test_initial_state_is_not_rate_limited(self):
        state = get_rate_limit_state()
        for p in ("groq", "gemini"):
            assert not state.get(p, {}).get("rate_limited", False)

    def test_mark_rate_limited(self):
        mark_rate_limited("groq", cooldown_seconds=10)
        state = get_rate_limit_state()
        assert state["groq"]["rate_limited"] == True

    def test_mark_provider_ok(self):
        mark_rate_limited("groq", cooldown_seconds=10)
        mark_provider_ok("groq")
        state = get_rate_limit_state()
        assert not state["groq"]["rate_limited"]

    def test_rate_limit_cooldown_expires(self):
        mark_rate_limited("groq", cooldown_seconds=0)
        import time
        time.sleep(0.01)
        state = get_rate_limit_state()
        assert not state.get("groq", {}).get("rate_limited", False)
