"""
Tests for flp.manifest (docs/CAPABILITY_MANIFEST_spec_v0.2.md).

The six conformance tests of spec §8, in order.

Run: python -m pytest tests/test_manifest.py -v
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from flp.identity import Identity  # noqa: E402
from flp.manifest import (  # noqa: E402
    CapabilityManifest,
    ManifestDiscloser,
    answer_challenge,
    band_mismatch,
    verify_manifest,
    verify_reveal,
    _leaf_hash,
    _root_sig_payload,
)
from flp.reputation import (  # noqa: E402
    Cooperation,
    ReputationLedger,
    Verdict,
    make_attestation,
)
from flp.cost_model import CostModel, CapabilityProfile, MatchedItem  # noqa: E402


CAPS = [
    {
        "id": "cabo.marine.port-status",
        "namespace": "cabo.marine",
        "disclosure": {
            "public": {
                "provides": "Port status and sea conditions for the Los Cabos corridor.",
                "use_when": ["requester needs to know whether the port is open"],
                "do_not_use_when": ["dining questions -> cabo.dining"],
                "cost_band": "low",
            },
            "known": {
                "input_schema": {"date": "ISO-8601", "zone": "enum"},
                "cost": {"unit": "per_call", "value": 0.002, "currency": "USD"},
                "constraints": ["rate: 60/min", "cache: 1h"],
            },
            "trusted": {
                "endpoint_hint": "https://cabo.example/port",
                "sla": "p95 < 300ms",
            },
        },
    }
]


def _manifest(identity=None):
    return CapabilityManifest.build(
        identity or Identity.generate(),
        CAPS,
        issued_at="2026-07-04T00:00:00Z",
        expires_at="2026-07-11T00:00:00Z",
    )


# --- §8.1 round-trip -------------------------------------------------------- #

def test_round_trip_public_only():
    announcer = Identity.generate()
    m = _manifest(announcer)
    bundle = m.reveal("public")
    assert verify_reveal(bundle, announcer.agent_id)
    # Baseline + public fields are present; matching layers 1-3 are fed.
    r = bundle["revealed"]
    assert r["agent.did"] == announcer.agent_id
    assert r["capabilities.0.id"] == "cabo.marine.port-status"
    assert r["capabilities.0.namespace"] == "cabo.marine"
    assert r["capabilities.0.disclosure.public.cost_band"] == "low"


def test_round_trip_all_tiers_same_root():
    announcer = Identity.generate()
    m = _manifest(announcer)
    roots = set()
    for tier in ("public", "known", "trusted"):
        bundle = m.reveal(tier)
        assert verify_reveal(bundle, announcer.agent_id)
        roots.add(bundle["commitment"]["root"])
    assert len(roots) == 1  # one signed manifest serves every trust level


# --- §8.2 tamper ------------------------------------------------------------ #

def test_tampered_field_fails_verification():
    announcer = Identity.generate()
    bundle = _manifest(announcer).reveal("public")
    bundle["revealed"]["capabilities.0.disclosure.public.cost_band"] = "high"
    assert not verify_reveal(bundle, announcer.agent_id)


def test_wrong_did_fails_verification():
    announcer = Identity.generate()
    bundle = _manifest(announcer).reveal("public")
    assert not verify_reveal(bundle, Identity.generate().agent_id)


# --- §8.3 hidden-leaf privacy ------------------------------------------------ #

def test_hidden_leaves_stay_hidden():
    announcer = Identity.generate()
    bundle = _manifest(announcer).reveal("public")
    # No known/trusted path, value, or salt ships with a public-only reveal.
    for path in list(bundle["revealed"]) + list(bundle["proofs"]):
        assert ".known." not in path and ".trusted." not in path

    # Dictionary attack: the receiver guesses the hidden exact cost. Without
    # the per-leaf salt, no candidate hash matches anything it holds.
    proof_hashes = {
        sib for p in bundle["proofs"].values() for _, sib in p["siblings"]
    }
    hidden_path = "capabilities.0.disclosure.known.cost"
    for guess_value in ({"unit": "per_call", "value": v, "currency": "USD"}
                        for v in (0.001, 0.002, 0.005, 0.01)):
        for guess_salt in (b"", b"\x00" * 16):
            h = _leaf_hash(hidden_path, guess_value, guess_salt).hex()
            assert h not in proof_hashes


# --- signature domain separation --------------------------------------------- #

def test_root_signature_is_domain_separated():
    """The key signs H(context || root), never the bare root, so manifest
    signatures and envelope signatures live in disjoint domains."""
    announcer = Identity.generate()
    m = _manifest(announcer)
    bundle = m.reveal("public")
    sig = bundle["signature"]["value"]
    root = bytes.fromhex(bundle["commitment"]["root"])

    # The signature covers the tagged payload only — not the bare root.
    assert Identity.verify_raw(announcer.agent_id, _root_sig_payload(root), sig)
    assert not Identity.verify_raw(announcer.agent_id, root, sig)

    # An envelope signature from the same key never verifies as a root sig.
    env = announcer.sign({"type": "outcome_attestation", "verdict": "fulfilled"})
    tampered = dict(bundle, signature={"alg": "Ed25519", "value": env.sig})
    assert not verify_reveal(tampered, announcer.agent_id)


# --- §8.4 challenge ---------------------------------------------------------- #

def _policy_serving(tier):
    return lambda requester_did: tier


def test_known_tier_requires_proof_of_key():
    announcer, requester = Identity.generate(), Identity.generate()
    disc = ManifestDiscloser(_manifest(announcer), _policy_serving("trusted"))

    # No challenge response: served the open tier only.
    served = disc.request(requester.agent_id, "known", challenge_response=None)
    assert not any(".known." in p for p in served["revealed"])

    # Response signed by the WRONG key (stolen did claim): open tier only.
    nonce = disc.challenge(requester.agent_id)
    mallory = Identity.generate()
    served = disc.request(requester.agent_id, "known",
                          challenge_response=answer_challenge(mallory, nonce))
    assert not any(".known." in p for p in served["revealed"])

    # Valid proof-of-key: the known tier unseals and verifies.
    nonce = disc.challenge(requester.agent_id)
    served = disc.request(requester.agent_id, "known",
                          challenge_response=answer_challenge(requester, nonce))
    assert any(".known." in p for p in served["revealed"])
    assert verify_reveal(served, announcer.agent_id)


def test_policy_caps_the_tier():
    announcer, requester = Identity.generate(), Identity.generate()
    # Announcer policy: this requester rates "known", never "trusted".
    disc = ManifestDiscloser(_manifest(announcer), _policy_serving("known"))
    nonce = disc.challenge(requester.agent_id)
    served = disc.request(requester.agent_id, "trusted",
                          challenge_response=answer_challenge(requester, nonce))
    assert any(".known." in p for p in served["revealed"])
    assert not any(".trusted." in p for p in served["revealed"])


# --- §8.5 inflated claim (unit form; N-trial harness version in T4) ---------- #

def _record_outcome(ledger, pid, a, b, verdict_a, verdict_b, now):
    coop = Cooperation(pid, a.agent_id, b.agent_id, started_at=now - 60)
    coop.add_attestation(make_attestation(a, pid, b.agent_id,
                                          verdict_a, issued_at=int(now)))
    coop.add_attestation(make_attestation(b, pid, a.agent_id,
                                          verdict_b, issued_at=int(now)))
    ledger.record(coop)


def test_inflated_claim_loses_reputation():
    """A liar whose `provides` overstates capability accepts, fails, and pays
    for it on the trust edge — closing the loop with PROTOCOL.md §6.7.

    Strangers sit at the trust floor (0.0), so "losing reputation" from zero
    means acquiring an evidence DEFICIT: after one identical good outcome
    each, the liar's trust stays strictly below a clean agent's. The lie is
    unprofitable; the N-trial profitability version runs in the harness (T4).
    """
    victim, liar, clean = Identity.generate(), Identity.generate(), Identity.generate()
    ledger = ReputationLedger(victim.agent_id)
    now = time.time()

    trust_stranger = ledger.trust(liar.agent_id, now=now)
    assert trust_stranger == 0.0  # newcomer floor (§3.2/§4.5)

    # Stranger + small magnitude clears the threshold (§5.4): the victim
    # rationally accepts a first small cooperation on the announced claim.
    model = CostModel(CapabilityProfile(default_solo_cost=8.0))
    item = MatchedItem(capability="cabo.marine.port-status", magnitude=2.0)
    assert model.evaluate_item(item, trust_stranger).cooperate

    # The liar cannot actually deliver; both sides close it as failed.
    _record_outcome(ledger, "coop-inflated-1", victim, liar,
                    Verdict.FAILED, Verdict.FAILED, now)
    assert ledger.trust(liar.agent_id, now=now) == 0.0  # pinned to the floor

    # One identical fulfilled cooperation each, afterwards:
    _record_outcome(ledger, "coop-liar-good", victim, liar,
                    Verdict.FULFILLED, Verdict.FULFILLED, now)
    _record_outcome(ledger, "coop-clean-good", victim, clean,
                    Verdict.FULFILLED, Verdict.FULFILLED, now)

    # The clean agent has earned trust; the liar is still digging out.
    assert ledger.trust(liar.agent_id, now=now) < ledger.trust(clean.agent_id, now=now)


# --- §8.6 provable lie: band vs. committed cost ------------------------------ #

def test_provable_lie_band_cost_mismatch():
    """Announcer commits a high cost but publishes cost_band 'low'. The
    mismatch is detected from the two verified proofs alone and produces a
    negative outcome record (spec §5: MUST count as a failed outcome)."""
    announcer = Identity.generate()
    lying_caps = [dict(CAPS[0], disclosure={
        "public": dict(CAPS[0]["disclosure"]["public"], cost_band="low"),
        "known": dict(CAPS[0]["disclosure"]["known"],
                      cost={"unit": "per_call", "value": 50.0, "currency": "USD"}),
        "trusted": CAPS[0]["disclosure"]["trusted"],
    })]
    m = CapabilityManifest.build(announcer, lying_caps,
                                 issued_at="2026-07-04T00:00:00Z",
                                 expires_at="2026-07-11T00:00:00Z")

    bundle = m.reveal("known")
    assert verify_reveal(bundle, announcer.agent_id)  # both leaves attributable

    band = bundle["revealed"]["capabilities.0.disclosure.public.cost_band"]
    cost = bundle["revealed"]["capabilities.0.disclosure.known.cost"]
    assert band_mismatch(band, cost)  # caught from the committed values alone

    # ...and the honest manifest raises no alarm.
    honest = _manifest(announcer).reveal("known")
    assert not band_mismatch(
        honest["revealed"]["capabilities.0.disclosure.public.cost_band"],
        honest["revealed"]["capabilities.0.disclosure.known.cost"],
    )

    # The mismatch feeds reputation as a failed outcome record: after the
    # penalty plus one good outcome, the liar still trails a clean agent
    # with the same single good outcome.
    victim, control = Identity.generate(), Identity.generate()
    ledger = ReputationLedger(victim.agent_id)
    now = time.time()
    _record_outcome(ledger, "coop-provable-lie", victim, announcer,
                    Verdict.FAILED, Verdict.FAILED, now)
    _record_outcome(ledger, "coop-liar-recovery", victim, announcer,
                    Verdict.FULFILLED, Verdict.FULFILLED, now)
    _record_outcome(ledger, "coop-control-good", victim, control,
                    Verdict.FULFILLED, Verdict.FULFILLED, now)
    assert (ledger.trust(announcer.agent_id, now=now)
            < ledger.trust(control.agent_id, now=now))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
