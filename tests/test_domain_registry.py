from brain.domain_registry import DomainRegistry


def test_routes_coding_query():
    registry = DomainRegistry()
    assert registry.route("how do I write a python function") == "CodingDomain"
    assert registry.route("fix this bug in my code") == "CodingDomain"
    assert registry.route("what is a class in java") == "CodingDomain"


def test_routes_game_query():
    registry = DomainRegistry()
    assert registry.route("best chess opening for beginners") == "GameDomain"
    assert registry.route("how to play connect 4") == "GameDomain"


def test_routes_general_query():
    registry = DomainRegistry()
    assert registry.route("what is the weather today") == "GeneralDomain"
    assert registry.route("tell me a joke") == "GeneralDomain"


def test_encode_coding():
    registry = DomainRegistry()
    result = registry.encode("write a python function")
    assert result["domain"] == "coding"
    assert result["language"] == "python"


def test_encode_game():
    registry = DomainRegistry()
    result = registry.encode("best chess opening")
    assert result["domain"] == "game"
    assert result["game_type"] == "chess"


def test_encode_general():
    registry = DomainRegistry()
    result = registry.encode("what is the weather")
    assert result["domain"] == "general"


def test_case_insensitive():
    registry = DomainRegistry()
    assert registry.route("PLAY chess") == "GameDomain"
    assert registry.route("DEBUG Python Code") == "CodingDomain"
