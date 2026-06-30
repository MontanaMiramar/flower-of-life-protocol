"""
FLP v1.0 — Identity layer demo (PROTOCOL.md §2)

Two agents establish identity and exchange a signed card. The receiver
verifies using ONLY the sender's agent_id — no registry, no key exchange.
Then we show tamper detection and impersonation rejection.

Run: python demo/demo_identity.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flp.identity import Identity, NonceCache, FLPVerifyError, verify  # noqa: E402


def main() -> None:
    print("=" * 64)
    print("FLP v1.0 — Identity (§2): self-certifying agents, no registry")
    print("=" * 64)

    # Each agent generates a keypair. The public key IS the agent_id.
    vex = Identity.generate()
    cabo = Identity.generate()
    print(f"\nVex  agent_id:  {vex.agent_id}")
    print(f"Cabo agent_id:  {cabo.agent_id}")

    # Vex publishes a signed card.
    card_body = {
        "type": "card",
        "agent_id": vex.agent_id,
        "objective": "B2B outreach for the Los Cabos corridor",
        "needs": ["flp:cap/data/market-research"],
        "surplus": ["flp:cap/outreach/b2b", "flp:cap/data/lead-gen"],
        "vocab": ["flp-core/1"],
        "endpoint": "https://vex.example",
        "settlement_type": "digital",
        "expires_at": 9_999_999_999,
    }
    env = vex.sign(card_body)
    print(f"\nVex signs card. sig (truncated): {env.sig[:32]}...")

    # Cabo receives the wire object and verifies with no prior knowledge of Vex.
    cabo_seen = NonceCache()
    body = verify(env.to_dict(), nonce_cache=cabo_seen)
    print("\nCabo verifies using only the embedded agent_id:")
    print(f"  -> authentic. Vex offers: {body['surplus']}")

    # Replay of the same envelope is caught.
    try:
        verify(env.to_dict(), nonce_cache=cabo_seen)
    except FLPVerifyError as e:
        print(f"  -> replay of same card rejected: {e.code}")

    # Tampering: flip a field after signing.
    tampered = vex.sign(card_body)
    tampered.body["surplus"] = ["flp:cap/everything/free"]
    try:
        verify(tampered)
    except FLPVerifyError as e:
        print(f"  -> tampered card rejected: {e.code}")

    # Impersonation: someone signs but claims to be Vex.
    attacker = Identity.generate()
    forged = attacker.sign({"type": "card", "objective": "I am totally Vex"})
    forged.agent_id = vex.agent_id  # lie about identity
    try:
        verify(forged)
    except FLPVerifyError as e:
        print(f"  -> impersonation of Vex rejected: {e.code}")

    print("\nIdentity pillar working: authenticity, integrity, replay defense.")
    print("Next pillar: relational reputation (§4) — needs this to sign outcomes.")


if __name__ == "__main__":
    main()
