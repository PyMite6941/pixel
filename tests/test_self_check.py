from self.self_check import health, capabilities, deps_status


class TestSelfCheck:
    def test_health_returns_dict(self):
        result = health()
        assert "status" in result
        assert "files_checked" in result
        assert "files_ok" in result
        assert result["files_checked"] >= 0

    def test_capabilities_returns_dict(self):
        result = capabilities()
        assert "domains" in result
        assert "skills" in result
        assert "providers" in result
        assert "features" in result
        assert "SelfDomain" in result["domains"]
        assert "think" in result["skills"]

    def test_deps_status_returns_list(self):
        result = deps_status()
        assert isinstance(result, list)
        for dep in result:
            assert "package" in dep
            assert "status" in dep
