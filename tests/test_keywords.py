from trendpulse.keywords import (channels_for, is_geo_relevant, is_question,
                                 normalize, seed_keywords, valid_candidate)

CFG = {"geo_terms": ["ai", "llm"], "seeds": {"seo": ["CRM Software"], "aeo": ["how to choose a crm"], "geo": ["ai agents"]}}


def test_normalize():
    assert normalize("  CRM  Software! ") == "crm software"
    assert normalize("AI-Agents?") == "ai-agents"


def test_is_question():
    assert is_question("how to choose a crm")
    assert is_question("what is aeo?")
    assert is_question("is seo dead")
    assert not is_question("crm software")


def test_is_geo_relevant():
    assert is_geo_relevant("best ai agents for seo")
    assert is_geo_relevant("llm optimization", ["llm"])
    assert not is_geo_relevant("crm software")


def test_channels_for():
    assert channels_for("crm software", CFG) == {"seo"}
    assert channels_for("how to choose a crm", CFG) == {"seo", "aeo"}
    assert channels_for("how do ai agents rank content", CFG) == {"seo", "aeo", "geo"}
    assert channels_for("crm software", CFG, seed_channel="geo") == {"seo", "geo"}


def test_seed_keywords_normalizes():
    seeds = seed_keywords(CFG)
    assert seeds["crm software"] == "seo"
    assert seeds["how to choose a crm"] == "aeo"


def test_valid_candidate():
    assert valid_candidate("crm software")
    assert not valid_candidate("ab")
    assert not valid_candidate("x " * 20)
