"""
Tests for flp.cost_model (PROTOCOL.md §5).

Run: python -m pytest tests/test_cost_model.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from flp.cost_model import (  # noqa: E402
    CostModel, CapabilityProfile, MatchedItem, risk,
    RISK_MAX, RISK_MIN,
)


# --- risk function (§5.3) -------------------------------------------------- #

def test_risk_endpoints():
    assert risk(0.0) == pytest.approx(RISK_MAX)     # stranger = max risk
    assert risk(1.0) == pytest.approx(RISK_MIN)     # proven peer = min risk

def test_risk_monotone_decreasing():
    assert risk(0.2) > risk(0.5) > risk(0.9)

def test_risk_clamps_out_of_range():
    assert risk(-5) == pytest.approx(RISK_MAX)
    assert risk(5) == pytest.approx(RISK_MIN)


# --- spec parity: the §5.5 worked example ---------------------------------- #

def test_spec_worked_example():
    """Reproduce PROTOCOL.md §5.5 exactly."""
    prof = CapabilityProfile(solo_cost={"market_data": 8.0}, transport_cost=1.0,
                             risk_max=1.0, risk_min=0.1)
    cm = CostModel(prof)

    # stranger, small ask: trust=0, mag=2 -> coop_cost 3 < 8 -> cooperate
    d = cm.evaluate_item(MatchedItem("market_data", magnitude=2), trust=0.0)
    assert d.coop_cost == pytest.approx(3.0)
    assert d.cooperate is True

    # stranger, large ask: mag=10 -> coop_cost 11 >= 8 -> pass
    d = cm.evaluate_item(MatchedItem("market_data", magnitude=10), trust=0.0)
    assert d.coop_cost == pytest.approx(11.0)
    assert d.cooperate is False

    # proven partner, large ask: trust=0.9 -> risk 0.19, mag=10 -> 2.9 < 8
    d = cm.evaluate_item(MatchedItem("market_data", magnitude=10), trust=0.9)
    assert d.coop_cost == pytest.approx(2.9)
    assert d.cooperate is True


# --- the equation bites: trust changes the outcome (§5.1, §5.4) ------------ #

def test_same_item_different_trust_flips_decision():
    cm = CostModel(CapabilityProfile(solo_cost={"c": 8.0}))
    item = MatchedItem("c", magnitude=10)
    assert cm.evaluate_item(item, trust=0.0).cooperate is False   # stranger: pass
    assert cm.evaluate_item(item, trust=0.9).cooperate is True    # peer: cooperate


# --- probation tier in arithmetic (§3.3, §5.4) ----------------------------- #

def test_probation_tier_caps_stranger_magnitude():
    cm = CostModel(CapabilityProfile(solo_cost={"c": 5.0}, transport_cost=1.0))
    # stranger (trust 0): cooperate iff 1 + 1.0*mag < 5 -> mag < 4
    assert cm.evaluate_item(MatchedItem("c", magnitude=3), 0.0).cooperate is True
    assert cm.evaluate_item(MatchedItem("c", magnitude=4), 0.0).cooperate is False

def test_max_safe_magnitude_grows_with_trust():
    cm = CostModel(CapabilityProfile(solo_cost={"c": 5.0}, transport_cost=1.0))
    small = cm.max_safe_magnitude("c", trust=0.0)
    large = cm.max_safe_magnitude("c", trust=0.9)
    assert small == pytest.approx(4.0)        # (5-1)/1.0
    assert large > small                       # trust unlocks bigger exchanges


# --- per-item mixing (§5.2) ------------------------------------------------ #

def test_one_encounter_mixes_cooperate_and_pass():
    prof = CapabilityProfile(solo_cost={"cheap_for_me": 2.0, "dear_for_me": 9.0})
    cm = CostModel(prof)
    items = [
        MatchedItem("cheap_for_me", magnitude=3),   # solo 2: not worth cooperating
        MatchedItem("dear_for_me", magnitude=3),    # solo 9: worth it
    ]
    decisions = {d.capability: d.cooperate for d in cm.evaluate(items, trust=0.3)}
    assert decisions["cheap_for_me"] is False
    assert decisions["dear_for_me"] is True

def test_proposal_items_returns_only_cleared():
    prof = CapabilityProfile(solo_cost={"a": 2.0, "b": 9.0})
    cm = CostModel(prof)
    items = [MatchedItem("a", magnitude=3), MatchedItem("b", magnitude=3)]
    cleared = cm.proposal_items(items, trust=0.3)
    assert [d.capability for d in cleared] == ["b"]


# --- match confidence raises effective risk (§6.7) ------------------------- #

def test_fuzzy_match_is_more_cautious():
    cm = CostModel(CapabilityProfile(solo_cost={"c": 5.0}, transport_cost=1.0))
    exact = cm.evaluate_item(MatchedItem("c", magnitude=3, match_confidence=1.0), 0.3)
    fuzzy = cm.evaluate_item(MatchedItem("c", magnitude=3, match_confidence=0.5), 0.3)
    assert fuzzy.effective_risk > exact.effective_risk
    assert fuzzy.coop_cost > exact.coop_cost

def test_fuzzy_match_can_flip_to_pass():
    cm = CostModel(CapabilityProfile(solo_cost={"c": 5.0}, transport_cost=1.0))
    # at trust 0.5, exact clears but a low-confidence fuzzy match may not
    exact = cm.evaluate_item(MatchedItem("c", magnitude=6, match_confidence=1.0), 0.5)
    fuzzy = cm.evaluate_item(MatchedItem("c", magnitude=6, match_confidence=0.4), 0.5)
    assert exact.cooperate is True
    assert fuzzy.cooperate is False


# --- defaults (§5.6) ------------------------------------------------------- #

def test_unknown_capability_uses_default_solo():
    cm = CostModel(CapabilityProfile(default_solo_cost=5.0))
    d = cm.evaluate_item(MatchedItem("never_configured", magnitude=1), trust=0.5)
    assert d.solo_cost == 5.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
