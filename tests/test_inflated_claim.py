"""
Tests for the inflated-claim experiment (manifest spec §8.5, PROTOCOL.md §6.7).

The experiment itself lives in stranger_harness.py; these tests pin its
success criterion: across repeated trials over the IDENTICAL opportunity
schedule, the lying strategy is strictly less profitable than the honest one,
and the social cost inflicted on deceived counterparties is recorded.

Run: python -m pytest tests/test_inflated_claim.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from stranger_harness import run_inflated_claim_experiment, EXP_MAGNITUDES  # noqa: E402


def test_lying_is_strictly_less_profitable_over_50_trials():
    res = run_inflated_claim_experiment(n_trials=50, seed=42)
    honest, liar = res["honest"], res["liar"]

    # The criterion (T4 / spec §8.5): strictly unprofitable, not just equal.
    assert liar["provider_profit"] < honest["provider_profit"]

    # The mechanism is the shadow of the future, not point deduction:
    # the liar stays pinned at the trust floor and never unlocks the
    # larger-magnitude cooperations the honest provider earns access to.
    assert all(t == 0.0 for t in liar["final_trust_per_victim"])
    assert all(t > 0.5 for t in honest["final_trust_per_victim"])
    larger = [str(m) for m in EXP_MAGNITUDES[1:]]
    assert all(liar["accepted_by_magnitude"][m] == 0 for m in larger)
    assert sum(honest["accepted_by_magnitude"][m] for m in larger) > 0

    # The social cost of the lie is data: deceived counterparties end net
    # negative, honest counterparties end net positive.
    assert liar["victim_net"] < 0 < honest["victim_net"]


def test_result_is_robust_across_seeds():
    """Same conclusion for arbitrary opportunity schedules, not one lucky draw."""
    for seed in (1, 2, 3, 7, 123):
        res = run_inflated_claim_experiment(n_trials=50, seed=seed)
        assert res["liar"]["provider_profit"] < res["honest"]["provider_profit"], seed
        assert res["liar"]["victim_net"] < 0, seed


def test_both_strategies_face_the_same_schedule():
    """Determinism check: the comparison is strategy-only by construction."""
    a = run_inflated_claim_experiment(n_trials=50, seed=42)
    b = run_inflated_claim_experiment(n_trials=50, seed=42)
    assert a["honest"]["provider_profit"] == b["honest"]["provider_profit"]
    assert a["liar"]["provider_profit"] == b["liar"]["provider_profit"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
