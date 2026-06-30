"""
Tests for flp.reputation (PROTOCOL.md §4).

Run: python -m pytest tests/test_reputation.py -v
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from flp.identity import Identity  # noqa: E402
from flp.reputation import (  # noqa: E402
    ReputationLedger,
    Cooperation,
    Verdict,
    CoopState,
    make_attestation,
    DANGLING_TIMEOUT_SEC,
)

NOW = 1_700_000_000.0


def _coop(pid, A: Identity, B: Identity, va, vb, started=None):
    """Build a resolved-ready cooperation with given verdicts (None = unsigned)."""
    c = Cooperation(pid, A.agent_id, B.agent_id,
                    started_at=started if started is not None else NOW - 10)
    if va is not None:
        c.add_attestation(make_attestation(A, pid, B.agent_id, va, issued_at=int(NOW - 5)))
    if vb is not None:
        c.add_attestation(make_attestation(B, pid, A.agent_id, vb, issued_at=int(NOW - 5)))
    return c


# --- newcomer floor (§3.2, §4.5) ------------------------------------------- #

def test_stranger_has_zero_trust():
    me, x = Identity.generate(), Identity.generate()
    led = ReputationLedger(me.agent_id)
    assert led.trust(x.agent_id, now=NOW) == 0.0


# --- direct trust curve (§3.2 rule 4, §5.4) -------------------------------- #

def test_direct_good_builds_trust():
    me, x = Identity.generate(), Identity.generate()
    led = ReputationLedger(me.agent_id)
    led.record(_coop("p1", me, x, Verdict.FULFILLED, Verdict.FULFILLED))
    t1 = led.trust(x.agent_id, now=NOW)
    assert 0 < t1 < 1
    led.record(_coop("p2", me, x, Verdict.FULFILLED, Verdict.FULFILLED))
    led.record(_coop("p3", me, x, Verdict.FULFILLED, Verdict.FULFILLED))
    t3 = led.trust(x.agent_id, now=NOW)
    assert t3 > t1                       # more good -> more trust
    # sub-linear: tripling good cooperations less than triples trust
    assert t3 < 3 * t1


def test_one_defection_craters_trust():
    me, x = Identity.generate(), Identity.generate()
    led = ReputationLedger(me.agent_id)
    for i in range(5):
        led.record(_coop(f"g{i}", me, x, Verdict.FULFILLED, Verdict.FULFILLED))
    before = led.trust(x.agent_id, now=NOW)
    led.record(_coop("bad", me, x, Verdict.FAILED, Verdict.FAILED))
    after = led.trust(x.agent_id, now=NOW)
    # one failure (W_BAD=6) outweighs five goods (W_GOOD=1 each) -> floor
    assert before > 0.5
    assert after == 0.0


# --- terminal states (§4.3-4.4) -------------------------------------------- #

def test_disputed_is_bad():
    me, x = Identity.generate(), Identity.generate()
    c = _coop("d", me, x, Verdict.FULFILLED, Verdict.FAILED)  # disagreement
    assert c.resolve(NOW).state == CoopState.CONFIRMED_BAD


def test_dangling_penalizes_non_signer():
    me, x = Identity.generate(), Identity.generate()
    # x never signs; past the grace window
    started = NOW - DANGLING_TIMEOUT_SEC - 100
    c = _coop("dang", me, x, Verdict.FULFILLED, None, started=started)
    r = c.resolve(NOW)
    assert r.state == CoopState.DANGLING
    assert r.penalized == x.agent_id      # the one who didn't sign

    led = ReputationLedger(me.agent_id)
    led.record(c)
    assert led.trust(x.agent_id, now=NOW) == 0.0   # soft negative -> floor here


def test_pending_within_grace():
    me, x = Identity.generate(), Identity.generate()
    c = _coop("pend", me, x, Verdict.FULFILLED, None, started=NOW - 10)
    assert c.resolve(NOW).state == CoopState.PENDING


# --- testimony propagation + distance decay (§4.5) ------------------------- #

def test_testimony_depth1_confers_some_trust():
    me, friend, x = Identity.generate(), Identity.generate(), Identity.generate()
    led = ReputationLedger(me.agent_id)
    # I trust friend directly; friend has a good edge with x; I never met x.
    led.record(_coop("mf", me, friend, Verdict.FULFILLED, Verdict.FULFILLED))
    led.record(_coop("fx", friend, x, Verdict.FULFILLED, Verdict.FULFILLED))
    t_x = led.trust(x.agent_id, now=NOW)
    t_friend = led.trust(friend.agent_id, now=NOW)
    assert t_x > 0                      # propagated trust reaches x
    assert t_x < t_friend               # but weaker than my direct trust in friend


def test_distance_decay_depth2_weaker_than_depth1():
    me, f1, f2, x = (Identity.generate() for _ in range(4))
    # me -good- f1 -good- f2 -good- x   (x is at distance 3 chain; reachable via depth-2 testifier f2)
    led = ReputationLedger(me.agent_id)
    led.record(_coop("a", me, f1, Verdict.FULFILLED, Verdict.FULFILLED))
    led.record(_coop("b", f1, f2, Verdict.FULFILLED, Verdict.FULFILLED))
    led.record(_coop("c", f2, x, Verdict.FULFILLED, Verdict.FULFILLED))
    t_f1 = led.trust(f1.agent_id, now=NOW)   # direct, depth 0
    t_f2 = led.trust(f2.agent_id, now=NOW)   # depth 1 testimony
    t_x = led.trust(x.agent_id, now=NOW)     # depth 2 testimony
    assert t_f1 > t_f2 > t_x > 0             # monotone decay with distance


def test_beyond_horizon_is_invisible():
    # chain longer than MAX_DEPTH=2 hops of testifier: x sits too far.
    me, f1, f2, f3, x = (Identity.generate() for _ in range(5))
    led = ReputationLedger(me.agent_id)
    led.record(_coop("a", me, f1, Verdict.FULFILLED, Verdict.FULFILLED))
    led.record(_coop("b", f1, f2, Verdict.FULFILLED, Verdict.FULFILLED))
    led.record(_coop("c", f2, f3, Verdict.FULFILLED, Verdict.FULFILLED))
    led.record(_coop("d", f3, x, Verdict.FULFILLED, Verdict.FULFILLED))  # x via depth-3 testifier
    assert led.trust(x.agent_id, now=NOW) == 0.0   # past horizon -> unreachable


# --- Sybil resistance for free (§4.5) -------------------------------------- #

def test_sybil_clique_cannot_reach_me():
    me = Identity.generate()
    sybils = [Identity.generate() for _ in range(6)]
    led = ReputationLedger(me.agent_id)
    # The clique signs mutual CONFIRMED_GOOD all day, vouching for sybils[0].
    for i in range(1, 6):
        led.record(_coop(f"s{i}", sybils[0], sybils[i],
                         Verdict.FULFILLED, Verdict.FULFILLED))
    # I have NO edge to any sybil. Their self-praise has no trusted path to me.
    assert led.trust(sybils[0].agent_id, now=NOW) == 0.0


# --- defamation resistance: negatives don't propagate (§4.3) --------------- #

def test_defamer_cannot_push_negative():
    me, friend, victim = (Identity.generate() for _ in range(3))
    led = ReputationLedger(me.agent_id)
    # I trust friend. I also have my own good history with victim.
    led.record(_coop("mf", me, friend, Verdict.FULFILLED, Verdict.FULFILLED))
    led.record(_coop("mv", me, victim, Verdict.FULFILLED, Verdict.FULFILLED))
    baseline = led.trust(victim.agent_id, now=NOW)
    # friend tries to defame victim with a (mutually?) bad outcome.
    # Even a disputed outcome friend<->victim is EDGE-LOCAL: it must not lower
    # MY trust in victim.
    led.record(_coop("fv", friend, victim, Verdict.FAILED, Verdict.FAILED))
    after = led.trust(victim.agent_id, now=NOW)
    assert after == baseline            # third-party negative did not propagate


# --- relational: two observers, two truths (§4.1) -------------------------- #

def test_trust_is_relational():
    a, b, x = (Identity.generate() for _ in range(3))
    # a has good history with x; b does not.
    coop = _coop("ax", a, x, Verdict.FULFILLED, Verdict.FULFILLED)
    led_a = ReputationLedger(a.agent_id); led_a.record(coop)
    led_b = ReputationLedger(b.agent_id); led_b.record(coop)
    assert led_a.trust(x.agent_id, observer=a.agent_id, now=NOW) > 0
    assert led_b.trust(x.agent_id, observer=b.agent_id, now=NOW) == 0.0


# --- time decay (§4.6) ----------------------------------------------------- #

def test_time_decay_weakens_old_evidence():
    me, x = Identity.generate(), Identity.generate()
    led = ReputationLedger(me.agent_id)
    pid = "old"
    c = Cooperation(pid, me.agent_id, x.agent_id, started_at=NOW - 10)
    old_ts = int(NOW - 180 * 86400)     # 180 days old = 2 half-lives
    c.add_attestation(make_attestation(me, pid, x.agent_id, Verdict.FULFILLED, issued_at=old_ts))
    c.add_attestation(make_attestation(x, pid, me.agent_id, Verdict.FULFILLED, issued_at=old_ts))
    led.record(c)
    t_old = led.trust(x.agent_id, now=NOW)

    led2 = ReputationLedger(me.agent_id)
    led2.record(_coop("fresh", me, x, Verdict.FULFILLED, Verdict.FULFILLED))
    t_fresh = led2.trust(x.agent_id, now=NOW)
    assert t_old < t_fresh               # aged evidence counts for less


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
