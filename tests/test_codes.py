import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from codes import TrialCodeManager, TrialCode, Redemption, WebsiteKey


class TestTrialCodeManager:
    def setup_method(self):
        self.manager = TrialCodeManager()

    def test_generate_code(self):
        code = self.manager.generate_code("admin", "pro")
        assert code.code.startswith("PX-")
        assert len(code.code) == 14  # PX-XXXXX-XXXXX
        assert code.tier == "pro"
        assert code.max_uses == 1
        assert code.active is True

    def test_generate_batch(self):
        codes = self.manager.generate_batch(5, "admin", "pro", 30)
        assert len(codes) == 5
        assert all(c.tier == "pro" for c in codes)

    def test_validate_valid_code(self):
        code = self.manager.generate_code("admin", "pro")
        result = self.manager.validate_code(code.code)
        assert result["valid"] is True
        assert result["tier"] == "pro"
        assert "days_remaining" in result

    def test_validate_nonexistent_code(self):
        result = self.manager.validate_code("PX-NOTEXIST-12345")
        assert result["valid"] is False
        assert "not found" in result["reason"]

    def test_validate_deactivated_code(self):
        code = self.manager.generate_code("admin", "pro")
        self.manager.deactivate_code(code.code)
        result = self.manager.validate_code(code.code)
        assert result["valid"] is False

    def test_validate_used_up_code(self):
        c = self.manager.generate_code("admin", "pro", max_uses=1)
        self.manager._codes[c.code].uses = 1
        result = self.manager.validate_code(c.code)
        assert result["valid"] is False

    def test_redeem_code(self):
        code = self.manager.generate_code("admin", "pro")
        result = self.manager.redeem_code(code.code, "user123", "px_testkey")
        assert result["success"] is True
        assert result["tier"] == "pro"
        assert result["days"] == 30

    def test_redeem_twice_fails(self):
        code = self.manager.generate_code("admin", "pro", max_uses=1)
        self.manager.redeem_code(code.code, "user1", "key1")
        result = self.manager.redeem_code(code.code, "user2", "key2")
        assert result["success"] is False

    def test_create_website_key(self):
        wk = self.manager.create_website_key("mywebsite.com")
        assert wk.name == "mywebsite.com"
        assert wk.key.startswith("ws_")
        assert wk.active is True

    def test_validate_website_key_valid(self):
        self.manager.create_website_key("test.com")
        wk = self.manager._website_keys["test.com"]
        validated = self.manager.validate_website_key(wk.key)
        assert validated is not None
        assert validated.name == "test.com"

    def test_validate_website_key_invalid(self):
        validated = self.manager.validate_website_key("ws_fakekey1234567890")
        assert validated is None

    def test_revoke_website_key(self):
        self.manager.create_website_key("revokable.com")
        assert self.manager.revoke_website_key("revokable.com") is True
        wk = self.manager._website_keys["revokable.com"]
        assert wk.active is False

    def test_list_codes(self):
        self.manager.generate_code("admin", "free")
        self.manager.generate_code("admin", "pro")
        codes = self.manager.list_codes()
        assert len(codes) >= 2

    def test_get_stats(self):
        self.manager.generate_code("admin", "pro")
        stats = self.manager.get_stats()
        assert stats["total_codes"] >= 1
        assert stats["trial_days"] == 30
        assert stats["trial_tier"] == "pro"

    def test_code_format(self):
        code = self.manager.generate_code("admin")
        parts = code.code.split("-")
        assert parts[0] == "PX"
        assert len(parts[1]) == 5
        assert len(parts[2]) == 5

    def test_batch_unique_codes(self):
        codes = self.manager.generate_batch(10)
        unique = set(c.code for c in codes)
        assert len(unique) == 10

    def test_redeem_updates_uses(self):
        code = self.manager.generate_code("admin", "pro")
        self.manager.redeem_code(code.code, "u1", "k1")
        assert self.manager._codes[code.code].uses == 1

    def test_redemption_stored(self):
        code = self.manager.generate_code("admin")
        self.manager.redeem_code(code.code, "u_abc", "k_xyz")
        redemptions = self.manager.list_redemptions()
        assert len(redemptions) >= 1
        assert redemptions[0]["user_id"] == "u_abc"
