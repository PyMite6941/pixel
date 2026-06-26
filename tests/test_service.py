import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAuthManager:
    def setup_method(self):
        from service import AuthManager
        self.auth = AuthManager()

    def test_create_user(self):
        user = self.auth.create_user("Test User", "test@example.com", "free")
        assert user.name == "Test User"
        assert user.email == "test@example.com"
        assert user.tier == "free"
        assert user.active is True

    def test_create_api_key(self):
        user = self.auth.create_user("Key User", "key@example.com")
        key = self.auth.create_api_key(user.user_id, "test-key")
        assert key.key.startswith("px_")
        assert key.user_id == user.user_id
        assert key.name == "test-key"

    def test_validate_key_valid(self):
        user = self.auth.create_user("Valid", "v@example.com")
        key = self.auth.create_api_key(user.user_id)
        validated = self.auth.validate_key(key.key)
        assert validated is not None
        assert validated.user_id == user.user_id

    def test_validate_key_invalid(self):
        validated = self.auth.validate_key("px_nonexistent12345678901234567890")
        assert validated is None

    def test_validate_key_revoked(self):
        user = self.auth.create_user("Revoc", "r@example.com")
        key = self.auth.create_api_key(user.user_id)
        self.auth.revoke_key(key.key)
        validated = self.auth.validate_key(key.key)
        assert validated is None

    def test_get_tier_free(self):
        user = self.auth.create_user("Free", "f@example.com", "free")
        tier = self.auth.get_tier(user)
        assert tier["requests_per_day"] == 100
        assert tier["providers"] == ["ollama", "groq"]

    def test_get_tier_pro(self):
        user = self.auth.create_user("Pro", "p@example.com", "pro")
        tier = self.auth.get_tier(user)
        assert tier["requests_per_day"] == 10_000

    def test_get_tier_enterprise(self):
        user = self.auth.create_user("Enterprise", "e@example.com", "enterprise")
        tier = self.auth.get_tier(user)
        assert tier["requests_per_day"] == 100_000

    def test_list_users(self):
        self.auth.create_user("A", "a@example.com")
        self.auth.create_user("B", "b@example.com")
        assert len(self.auth.list_users()) >= 2

    def test_create_multiple_keys(self):
        user = self.auth.create_user("Multikey", "mk@example.com")
        k1 = self.auth.create_api_key(user.user_id, "key1")
        k2 = self.auth.create_api_key(user.user_id, "key2")
        assert k1.key != k2.key


class TestUsageTracker:
    def setup_method(self):
        from service import UsageTracker
        self.tracker = UsageTracker()
        self._uid_counter = 0

    def _uid(self):
        self._uid_counter += 1
        return f"test_user_{self._uid_counter}_{id(self)}"

    def test_track_usage(self):
        uid = self._uid()
        self.tracker.track(uid, "key1", input_tokens=100, output_tokens=50, cost=0.001)
        usage = self.tracker.get_usage(uid)
        assert usage is not None
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.requests == 1
        assert usage.cost == 0.001

    def test_track_multiple(self):
        uid = self._uid()
        self.tracker.track(uid, "key2", input_tokens=100, output_tokens=50, cost=0.001)
        self.tracker.track(uid, "key2", input_tokens=200, output_tokens=100, cost=0.002)
        usage = self.tracker.get_usage(uid)
        assert usage.input_tokens == 300
        assert usage.requests == 2

    def test_get_usage_nonexistent(self):
        uid = self._uid()
        usage = self.tracker.get_usage(uid)
        assert usage is None

    def test_check_limits_within(self):
        from service import AuthManager, TIER_LIMITS
        auth = AuthManager()
        user = auth.create_user("Limits", "limits@example.com", "free")
        checks = self.tracker.check_limits(user)
        assert checks["within_limits"] is True

    def test_check_limits_exceeded(self):
        from service import AuthManager, TIER_LIMITS
        auth = AuthManager()
        uid = self._uid()
        user = auth.create_user("Exceed", "ex@example.com", "free")
        user.user_id = uid
        tier = TIER_LIMITS["free"]
        self.tracker.track(uid, "keyx", input_tokens=tier["tokens_per_month"] + 1)
        checks = self.tracker.check_limits(user)
        assert checks["within_limits"] is False


class TestTierLimits:
    def test_all_tiers_defined(self):
        from service import TIER_LIMITS
        assert "free" in TIER_LIMITS
        assert "pro" in TIER_LIMITS
        assert "enterprise" in TIER_LIMITS

    def test_tier_escalation(self):
        from service import TIER_LIMITS
        assert TIER_LIMITS["free"]["requests_per_day"] < TIER_LIMITS["pro"]["requests_per_day"]
        assert TIER_LIMITS["pro"]["tokens_per_month"] < TIER_LIMITS["enterprise"]["tokens_per_month"]
        assert TIER_LIMITS["free"]["concurrent_requests"] < TIER_LIMITS["pro"]["concurrent_requests"]

    def test_tier_providers(self):
        from service import TIER_LIMITS
        assert "ollama" in TIER_LIMITS["free"]["providers"]
        assert "claude" not in TIER_LIMITS["free"]["providers"]
        assert "claude" in TIER_LIMITS["pro"]["providers"]
