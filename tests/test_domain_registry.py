from brain.domain_registry import DomainRegistry


class TestDomainRegistryRouting:
    def setup_method(self):
        self.registry = DomainRegistry()

    def test_routes_coding_query(self):
        assert self.registry.route("write a python function") == "CodingDomain"

    def test_routes_security_query(self):
        assert self.registry.route("how do i encrypt a file") == "SecurityDomain"

    def test_routes_self_query(self):
        assert self.registry.route("what are your capabilities") == "SelfDomain"

    def test_routes_game_query(self):
        assert self.registry.route("how to play chess") == "GameDomain"

    def test_routes_math_query(self):
        assert self.registry.route("calculate the derivative of x^2") == "MathDomain"

    def test_routes_writing_query(self):
        assert self.registry.route("write an essay about AI") == "WritingDomain"

    def test_routes_data_query(self):
        assert self.registry.route("analyze this csv file") == "DataDomain"

    def test_routes_research_query(self):
        assert self.registry.route("research quantum computing") == "ResearchDomain"

    def test_routes_general_fallback(self):
        assert self.registry.route("hello how are you") == "GeneralDomain"


class TestDomainRegistryEncode:
    def setup_method(self):
        self.registry = DomainRegistry()

    def test_encode_coding(self):
        result = self.registry.encode("write a python function")
        assert result["domain"] == "coding"
        assert result["language"] == "python"

    def test_encode_security(self):
        result = self.registry.encode("how do i encrypt data")
        assert result["domain"] == "security"
        assert result["subdomain"] == "cryptography"

    def test_encode_self(self):
        result = self.registry.encode("run a self check")
        assert result["domain"] == "self"
        assert result["subdomain"] == "self_check"

    def test_encode_game_chess(self):
        result = self.registry.encode("chess strategy")
        assert result["domain"] == "game"
        assert result["game_type"] == "chess"

    def test_encode_game_connect4(self):
        result = self.registry.encode("connect 4 strategy")
        assert result["domain"] == "game"
        assert result["game_type"] == "connect4"

    def test_encode_math_statistics(self):
        result = self.registry.encode("calculate standard deviation")
        assert result["domain"] == "math"
        assert result["subdomain"] == "statistics"

    def test_encode_writing_translation(self):
        result = self.registry.encode("translate hello to spanish")
        assert result["domain"] == "writing"
        assert result["subdomain"] == "translation"

    def test_encode_data_database(self):
        result = self.registry.encode("optimize a sql query")
        assert result["domain"] == "data"
        assert result["subdomain"] == "database"

    def test_encode_research_citations(self):
        result = self.registry.encode("find citation for this paper")
        assert result["domain"] == "research"
        assert result["subdomain"] == "citations"

    def test_encode_general(self):
        result = self.registry.encode("hello")
        assert result["domain"] == "general"
