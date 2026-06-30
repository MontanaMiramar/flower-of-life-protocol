"""
Tests for flp.identity (PROTOCOL.md §2).

Run: python -m pytest tests/test_identity.py -v
or:  python tests/test_identity.py   (standalone runner at bottom)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from flp.identity import (  # noqa: E402
    Identity,
    Envelope,
    NonceCache,
    FLPVerifyError,
    encode_did_key,
    decode_did_key,
    canonical,
    verify,
)


# --- did:key self-certifying identity (§2.2) ------------------------------- #

def test_did_key_roundtrip():
    ident = Identity.generate()
    pub = decode_did_key(ident.agent_id)
    # Re-encoding the decoded key reproduces the same agent_id.
    assert encode_did_key(pub) == ident.agent_id


def test_agent_id_shape():
    ident = Identity.generate()
    assert ident.agent_id.startswith("did:key:z6Mk")  # ed25519 multicodec marker


def test_identity_restore_from_seed():
    a = Identity.generate()
    b = Identity.from_private_bytes(a.private_bytes())
    assert a.agent_id == b.agent_id  # same key => same identity


def test_no_registry_needed():
    """A verifier with ONLY the agent_id string can verify — no lookup."""
    signer = Identity.generate()
    env = signer.sign({"type": "card", "objective": "demo"})
    # Verifier never met signer, has no key store; agent_id is enough.
    body = verify(env)
    assert body["objective"] == "demo"


# --- sign / verify happy path (§2.3) --------------------------------------- #

def test_sign_verify_roundtrip():
    ident = Identity.generate()
    env = ident.sign({"type": "card", "needs": ["flp:cap/data/x"]})
    body = verify(env)
    assert body["needs"] == ["flp:cap/data/x"]
    assert "issued_at" in body and "nonce" in body


def test_envelope_dict_roundtrip():
    ident = Identity.generate()
    env = ident.sign({"type": "card"})
    wire = env.to_dict()
    restored = Envelope.from_dict(wire)
    assert verify(restored)["type"] == "card"


# --- JCS determinism (§2.3) ------------------------------------------------ #

def test_canonical_key_order_independent():
    a = canonical({"b": 1, "a": 2, "nested": {"y": 1, "x": 2}})
    b = canonical({"a": 2, "nested": {"x": 2, "y": 1}, "b": 1})
    assert a == b  # JCS sorts keys => identical bytes regardless of input order


def test_signature_survives_key_reordering():
    """A re-serialized body with different key order still verifies."""
    ident = Identity.generate()
    env = ident.sign({"type": "card", "z": 1, "a": 2})
    reordered = {k: env.body[k] for k in reversed(list(env.body.keys()))}
    env2 = Envelope(env.flp_version, reordered, env.agent_id, env.sig)
    assert verify(env2)["type"] == "card"  # JCS makes order irrelevant


# --- tamper / impersonation (threat model §1.1) ---------------------------- #

def test_tamper_body_rejected():
    ident = Identity.generate()
    env = ident.sign({"type": "card", "needs": ["flp:cap/data/x"]})
    env.body["needs"] = ["flp:cap/data/HACKED"]  # mutate after signing
    with pytest.raises(FLPVerifyError) as ei:
        verify(env)
    assert ei.value.code == "invalid_signature"


def test_impersonation_rejected():
    """Sign with A's key but claim B's agent_id => signature fails."""
    a = Identity.generate()
    b = Identity.generate()
    env = a.sign({"type": "card"})
    env.agent_id = b.agent_id  # claim to be B
    with pytest.raises(FLPVerifyError) as ei:
        verify(env)
    assert ei.value.code == "invalid_signature"


def test_malformed_agent_id_rejected():
    ident = Identity.generate()
    env = ident.sign({"type": "card"})
    env.agent_id = "did:key:zNOTAREALKEY"
    with pytest.raises(FLPVerifyError) as ei:
        verify(env)
    assert ei.value.code == "validation_failed"


# --- freshness + replay (§2.4) --------------------------------------------- #

def test_expired_rejected():
    ident = Identity.generate()
    env = ident.sign({"type": "card", "expires_at": int(time.time()) - 10})
    with pytest.raises(FLPVerifyError) as ei:
        verify(env)
    assert ei.value.code == "expired"


def test_future_issued_at_rejected():
    ident = Identity.generate()
    env = ident.sign({"type": "card", "issued_at": int(time.time()) + 10_000})
    with pytest.raises(FLPVerifyError) as ei:
        verify(env)
    assert ei.value.code == "validation_failed"


def test_replay_rejected():
    ident = Identity.generate()
    cache = NonceCache()
    env = ident.sign({"type": "card"})
    verify(env, nonce_cache=cache)                 # first sight: ok
    with pytest.raises(FLPVerifyError) as ei:      # second sight: replay
        verify(env, nonce_cache=cache)
    assert ei.value.code == "replay_detected"


def test_distinct_nonces_not_replay():
    ident = Identity.generate()
    cache = NonceCache()
    verify(ident.sign({"type": "card"}), nonce_cache=cache)
    verify(ident.sign({"type": "card"}), nonce_cache=cache)  # different nonce: ok


def test_nonce_eviction_allows_resight_after_window():
    ident = Identity.generate()
    cache = NonceCache(window_sec=1)
    env = ident.sign({"type": "card"})
    t0 = time.time()
    verify(env, nonce_cache=cache, now=t0, require_fresh=False)
    # After the window, the nonce is evicted; not treated as replay.
    verify(env, nonce_cache=cache, now=t0 + 5, require_fresh=False)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
