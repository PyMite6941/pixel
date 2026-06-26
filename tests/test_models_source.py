import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.source import AgentSource, get_default_sources, resolve_agent_source


class TestAgentSource:
    def test_default_sources_have_default(self):
        sources = get_default_sources()
        assert any(s.name == "default" for s in sources)
        assert any(s.name == "coding" for s in sources)
        assert any(s.name == "security" for s in sources)
        assert any(s.name == "reasoning" for s in sources)

    def test_resolve_primary_api(self):
        sources = [
            AgentSource(name="default", primary_api="groq", fallback_images=[]),
        ]
        result = resolve_agent_source("default", sources, ["groq", "ollama"], [])
        assert result == "groq"

    def test_resolve_preferred_overrides_primary(self):
        sources = [
            AgentSource(name="default", primary_api="groq", fallback_images=[], preferred="ollama"),
        ]
        result = resolve_agent_source("default", sources, ["groq", "ollama"], [])
        assert result == "ollama"

    def test_resolve_fallback_when_primary_unavailable(self):
        sources = [
            AgentSource(name="default", primary_api="claude", fallback_images=["ollama"]),
        ]
        result = resolve_agent_source("default", sources, ["groq", "ollama"], [])
        assert result == "ollama"

    def test_resolve_fallback_to_local_image(self):
        sources = [
            AgentSource(name="default", primary_api="claude", fallback_images=["my_local_model"]),
        ]
        result = resolve_agent_source("default", sources, ["groq"], ["my_local_model"])
        assert result == "my_local_model"

    def test_resolve_fallback_to_first_available(self):
        sources = [
            AgentSource(name="default", primary_api="claude", fallback_images=["nope1", "nope2"]),
        ]
        result = resolve_agent_source("default", sources, ["groq"], [])
        assert result == "groq"

    def test_resolve_unknown_agent_uses_first_available(self):
        sources = [
            AgentSource(name="default", primary_api="groq", fallback_images=[]),
        ]
        result = resolve_agent_source("unknown_agent", sources, ["ollama"], [])
        assert result == "ollama"

    def test_resolve_no_providers_returns_ollama(self):
        sources = [AgentSource(name="default")]
        result = resolve_agent_source("default", sources, [], [])
        assert result == "ollama"

    def test_agent_source_to_dict_roundtrip(self):
        src = AgentSource(name="test", primary_api="groq", fallback_images=["fb1", "fb2"], preferred="fb1")
        d = src.to_dict()
        assert d["name"] == "test"
        assert d["primary_api"] == "groq"

        src2 = AgentSource.from_dict(d)
        assert src2.name == "test"
        assert src2.primary_api == "groq"
        assert src2.preferred == "fb1"

    def test_resolved_provider_preferred(self):
        src = AgentSource(name="t", primary_api="a", preferred="b")
        assert src.resolved_provider == "b"

    def test_resolved_provider_fallback_to_primary(self):
        src = AgentSource(name="t", primary_api="a")
        assert src.resolved_provider == "a"
