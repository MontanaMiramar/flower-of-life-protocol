"""
Tests for flp.server / flp.agent / flp.net (PROTOCOL.md §7.5, §8).

Run: python -m pytest tests/test_server.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from flp.identity import Identity, FLPVerifyError, verify  # noqa: E402
from flp.cost_model import CapabilityProfile  # noqa: E402
from flp.agent import FLPAgent, tolerant, _KNOWN_CARD_FIELDS  # noqa: E402
from flp.server import FLPServer, FLPClient  # noqa: E402
from flp.net import validate_endpoint  # noqa: E402


# --- SSRF guard (§7.5) ----------------------------------------------------- #

def test_ssrf_blocks_http_scheme():
    with pytest.raises(FLPVerifyError) as ei:
        validate_endpoint("http://example.com/x")
    assert ei.value.code == "ssrf_blocked"

def test_ssrf_blocks_loopback():
    with pytest.raises(FLPVerifyError):
        validate_endpoint("https://localhost/x", _resolver=lambda h: ["127.0.0.1"])

def test_ssrf_blocks_metadata_ip():
    with pytest.raises(FLPVerifyError):
        validate_endpoint("https://meta.evil/x", _resolver=lambda h: ["169.254.169.254"])

def test_ssrf_blocks_rfc1918():
    for ip in ["10.0.0.5", "192.168.1.1", "172.16.9.9"]:
        with pytest.raises(FLPVerifyError):
            validate_endpoint("https://internal/x", _resolver=lambda h, _ip=ip: [_ip])

def test_ssrf_allows_public_https():
    url = validate_endpoint("https://vex.example/x", _resolver=lambda h: ["93.184.216.34"])
    assert url.startswith("https://")

def test_ssrf_dev_override_allows_loopback():
    url = validate_endpoint("http://127.0.0.1:8000/x", allow_private=True)
    assert url.startswith("http://127.0.0.1")


# --- tolerant deserialization (§8.2) --------------------------------------- #

def test_tolerant_drops_unknown_fields():
    data = {"type": "card", "needs": [], "FUTURE_v2_field": "ignored"}
    out = tolerant(data, _KNOWN_CARD_FIELDS)
    assert "FUTURE_v2_field" not in out
    assert out["type"] == "card"

def test_agent_handles_card_with_future_fields():
    """A v1.1 card with extra fields must not crash a v1.0 agent."""
    a = _agent("a", needs=["flp:cap/data/x"], surplus=[])
    b = _agent("b", needs=[], surplus=["flp:cap/data/x"])
    card = b.identity.sign({**b.card_body(), "v2_feature": {"nested": 1}}).to_dict()
    resp = a.handle_encounter(card)          # would TypeError in v0.1
    assert resp["body"]["type"] in ("proposal", "response")


# --- helpers --------------------------------------------------------------- #

def _agent(_name, needs, surplus, solo=None):
    ident = Identity.generate()
    prof = CapabilityProfile(solo_cost=solo or {}, transport_cost=1.0)
    return FLPAgent(identity=ident, needs=needs, surplus=surplus,
                    endpoint="https://x.example", profile=prof)


# --- live HTTP round-trip (§8.4) ------------------------------------------- #

@pytest.fixture
def two_agents():
    # Cabo needs market-research (expensive solo); offers venue data.
    cabo = _agent("cabo",
                  needs=["flp:cap/data/market-research"],
                  surplus=["flp:cap/tourism/venue-availability"],
                  solo={"flp:cap/data/market-research": 8.0})
    # Vex offers a vocab-synonym of cabo's need; needs venue data.
    vex = _agent("vex",
                 needs=["flp:cap/tourism/venue-availability"],
                 surplus=["flp:cap/data/market-intelligence"],
                 solo={"flp:cap/tourism/venue-availability": 8.0})
    sv_cabo = FLPServer(cabo).start()
    sv_vex = FLPServer(vex).start()
    yield cabo, vex, sv_cabo, sv_vex
    sv_cabo.stop()
    sv_vex.stop()


def test_card_fetch_and_verify(two_agents):
    cabo, vex, sv_cabo, sv_vex = two_agents
    client = FLPClient(allow_private=True)
    card = client.fetch_card(sv_vex.base_url)
    body = verify(card)                       # self-certifying, no registry
    assert body["agent_id"] == vex.identity.agent_id


def test_status_exposes_version(two_agents):
    cabo, vex, sv_cabo, sv_vex = two_agents
    client = FLPClient(allow_private=True)
    st = client.status(sv_vex.base_url)
    assert st["flp_version"] == "1.0"
    assert "flp-core/1" in st["vocab"]


def test_full_encounter_proposal_flow(two_agents):
    cabo, vex, sv_cabo, sv_vex = two_agents
    client = FLPClient(allow_private=True)

    # Cabo encounters Vex: sends its signed card, gets a signed proposal back.
    proposal = client.encounter(sv_vex.base_url, cabo.signed_card())
    pbody = verify(proposal)
    assert pbody["type"] == "proposal"
    caps = {it["capability"] for it in pbody["items"]}
    # Vex should offer market-intelligence (matches Cabo's need) and want venue data
    assert "flp:cap/data/market-intelligence" in caps or \
           "flp:cap/tourism/venue-availability" in caps


def test_stranger_low_trust_round_trip(two_agents):
    """Between strangers, a small exchange clears; the wire path works end-to-end."""
    cabo, vex, sv_cabo, sv_vex = two_agents
    client = FLPClient(allow_private=True)
    proposal = client.encounter(sv_vex.base_url, cabo.signed_card())
    response = client.respond(sv_cabo.base_url, proposal)
    rbody = verify(response)
    assert rbody["type"] == "response"
    assert rbody["decision"] in ("accept", "counter", "decline")


def test_tampered_card_rejected_over_http(two_agents):
    cabo, vex, sv_cabo, sv_vex = two_agents
    client = FLPClient(allow_private=True)
    card = cabo.signed_card()
    card["body"]["surplus"] = ["flp:cap/everything/free"]   # tamper post-signing
    resp = client.encounter(sv_vex.base_url, card)
    assert resp.get("code") == "invalid_signature"          # §8.6 error


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
