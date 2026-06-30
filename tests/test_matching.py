"""
Tests for flp.matching (PROTOCOL.md §6).

Run: python -m pytest tests/test_matching.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from flp.matching import (  # noqa: E402
    Capability, Vocabulary, Matcher,
    EXACT_CONFIDENCE, VOCAB_CONFIDENCE, SEMANTIC_MAX_CONFIDENCE,
)


# --- capability URI parsing (§6.3) ----------------------------------------- #

def test_parse_valid_uri():
    c = Capability.parse("flp:cap/data/market-research")
    assert c.domain == "data"
    assert c.path == "market-research"

def test_parse_normalizes_case_and_space():
    c = Capability.parse("  FLP:CAP/Data/Market-Research  ")
    assert c.raw == "flp:cap/data/market-research"

def test_parse_rejects_bare_token():
    # v0.1's fragility: bare words are no longer valid capabilities
    assert not Capability.is_valid("market_intelligence")
    with pytest.raises(ValueError):
        Capability.parse("market_intelligence")

def test_parse_rejects_missing_domain():
    assert not Capability.is_valid("flp:cap/onlydomain")

def test_nested_path_allowed():
    c = Capability.parse("flp:cap/lang/translation/es-quechua")
    assert c.domain == "lang"
    assert c.path == "translation/es-quechua"


# --- Layer 1: exact match (§6.3) ------------------------------------------- #

def test_exact_match_full_confidence():
    m = Matcher()
    c = m.confidence("flp:cap/data/market-research", "flp:cap/data/market-research")
    assert c == EXACT_CONFIDENCE

def test_no_match_returns_none():
    m = Matcher()
    assert m.confidence("flp:cap/data/x", "flp:cap/tourism/y") is None

def test_exact_match_is_case_insensitive():
    m = Matcher()
    assert m.confidence("flp:cap/data/X", "FLP:CAP/DATA/x") == EXACT_CONFIDENCE


# --- Layer 2: vocabulary synonyms (§6.4) ----------------------------------- #

def test_vocab_synonym_match():
    m = Matcher(vocab=Vocabulary.core())
    # different URIs, same canonical concept
    c = m.confidence("flp:cap/data/market-research",
                     "flp:cap/data/market-intelligence")
    assert c == VOCAB_CONFIDENCE

def test_vocab_match_is_below_exact():
    assert VOCAB_CONFIDENCE < EXACT_CONFIDENCE

def test_unknown_uris_dont_vocab_match():
    m = Matcher(vocab=Vocabulary.core())
    assert m.confidence("flp:cap/foo/bar", "flp:cap/foo/baz") is None

def test_forkable_vocabulary_extension():
    # anyone can fork/extend with no approval gate
    v = Vocabulary({"flp:cap/farm/tomatoes": ["flp:cap/farm/tomato-produce"]})
    m = Matcher(vocab=v)
    assert m.confidence("flp:cap/farm/tomatoes",
                        "flp:cap/farm/tomato-produce") == VOCAB_CONFIDENCE


# --- Layer 3: local semantic, opt-in & capped (§6.5) ----------------------- #

def test_no_semantic_layer_by_default():
    m = Matcher(vocab=Vocabulary.core())
    # unrelated-by-vocab pair: no semantic matcher -> no match
    assert m.confidence("flp:cap/data/scraping", "flp:cap/data/web-harvest") is None

def test_semantic_layer_when_provided():
    def sem(a, b):
        return 0.9 if "scrap" in a and "harvest" in b else None
    m = Matcher(semantic=sem)
    c = m.confidence("flp:cap/data/scraping", "flp:cap/data/web-harvest")
    # capped at semantic_max even though the matcher returned 0.9
    assert c == SEMANTIC_MAX_CONFIDENCE

def test_semantic_is_advisory_below_exact_and_vocab():
    assert SEMANTIC_MAX_CONFIDENCE < VOCAB_CONFIDENCE < EXACT_CONFIDENCE

def test_layers_prefer_higher_confidence():
    # exact should win even if a semantic matcher also fires
    m = Matcher(vocab=Vocabulary.core(), semantic=lambda a, b: 0.5)
    assert m.confidence("flp:cap/data/x", "flp:cap/data/x") == EXACT_CONFIDENCE


# --- matching cards, two-sided (§6.6) -------------------------------------- #

def test_match_cards_both_directions():
    m = Matcher(vocab=Vocabulary.core())
    cabo = {
        "needs": ["flp:cap/data/market-research"],
        "surplus": ["flp:cap/tourism/venue-availability"],
    }
    vex = {
        "needs": ["flp:cap/tourism/venue-availability"],
        "surplus": ["flp:cap/data/market-intelligence"],  # vocab-synonym of cabo's need
    }
    res = m.match_cards(cabo, vex)
    need = {i.capability: i for i in res["i_need"]}
    offer = {i.capability: i for i in res["i_offer"]}
    assert "flp:cap/data/market-research" in need
    assert need["flp:cap/data/market-research"].match_confidence == VOCAB_CONFIDENCE
    assert "flp:cap/tourism/venue-availability" in offer
    assert offer["flp:cap/tourism/venue-availability"].match_confidence == EXACT_CONFIDENCE

def test_no_overlap_yields_nothing():
    m = Matcher()
    a = {"needs": ["flp:cap/data/x"], "surplus": ["flp:cap/data/y"]}
    b = {"needs": ["flp:cap/data/z"], "surplus": ["flp:cap/data/w"]}
    res = m.match_cards(a, b)
    assert res["i_need"] == [] and res["i_offer"] == []

def test_magnitudes_attached():
    m = Matcher()
    a = {"needs": ["flp:cap/data/x"], "surplus": []}
    b = {"needs": [], "surplus": ["flp:cap/data/x"]}
    res = m.match_cards(a, b, my_magnitudes={"flp:cap/data/x": 7.0})
    assert res["i_need"][0].magnitude == 7.0


# --- adversarial: matching never confers trust (§6.6) ---------------------- #

def test_match_confidence_independent_of_any_trust():
    """The matcher has no access to reputation; confidence is purely topical.

    An inflated surplus matches exactly like an honest one — which is fine,
    because the cost model + reputation (not the matcher) gate whether to act.
    """
    m = Matcher()
    honest = m.confidence("flp:cap/data/x", "flp:cap/data/x")
    liar = m.confidence("flp:cap/data/x", "flp:cap/data/x")  # liar claims same
    assert honest == liar == EXACT_CONFIDENCE
    # nothing in this module imports or consults reputation
    import flp.matching as mm
    assert "reputation" not in dir(mm)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
