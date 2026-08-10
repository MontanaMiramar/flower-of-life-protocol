"""
FLP v1.1 — Live handshake with a real stranger (PROTOCOL.md §8)

Run this from a clean machine and complete a full, signed FLP cooperation over
the open internet with an agent you have never met: `flpambassador`, the live
reference node.

    fetch card -> encounter -> proposal -> respond -> outcome -> attestation

You bring nothing but the protocol: you generate your own did:key, declare a
tiny capability card, and walk away with a signed *attestation* you can verify
anywhere — no registry, no account, no permission from anyone.

Honest framing: the attestation certifies that you and `flpambassador`
*completed an FLP protocol exchange and both attested the outcome* — NOT that
real work was delivered. Reputation is earned over repeated bilateral history,
not from a single signature (PROTOCOL.md §4).

Run:  python demo/demo_live_handshake.py
      python demo/demo_live_handshake.py https://flp.rodagentic.com   # default
      FLP_ENDPOINT=https://flp.rodagentic.com python demo/demo_live_handshake.py
"""

import json
import os
import sys
from pathlib import Path

# Works whether FLP is pip-installed or run straight from a clone.
try:
    import flp  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flp import (  # noqa: E402
    Identity, FLPAgent, FLPClient, CapabilityProfile,
    make_attestation, Verdict, verify, Envelope, FLPVerifyError,
)

DEFAULT_ENDPOINT = "https://flp.rodagentic.com"


def banner(s: str) -> None:
    print("\n" + "-" * 72 + f"\n{s}\n" + "-" * 72)


def main(endpoint: str) -> int:
    print("=" * 72)
    print(f"FLP v1.1 — Live handshake with a stranger @ {endpoint}")
    print("=" * 72)

    # YOU: a brand-new agent. Your key IS your identity — no registry (§2).
    # Edit needs/surplus freely; these complement what the ambassador offers/needs
    # so the encounter clears to a proposal.
    me = FLPAgent(
        identity=Identity.generate(),
        objective="Curious stranger trying FLP for the first time",
        needs=["flp:cap/knowledge/flp-protocol"],     # something the ambassador offers
        surplus=["flp:cap/data/market-research"],     # something it needs
        endpoint="https://your-node.example",         # where peers would reach YOU (unused here)
        profile=CapabilityProfile(
            solo_cost={"flp:cap/knowledge/flp-protocol": 8.0}, transport_cost=1.0),
        magnitudes={"flp:cap/data/market-research": 3.0},
    )
    print(f"\nYour fresh did:key:  {me.identity.agent_id}")

    # Production SSRF guard: https-only, no private / loopback / metadata IPs (§7.5).
    client = FLPClient(allow_private=False, timeout=10)

    banner("1. Fetch the stranger's signed card and verify it — no registry (§2.2 / §7.2)")
    card = client.fetch_card(endpoint)
    cbody = verify(card)
    peer_id = cbody["agent_id"]
    print(f"  Verified. Card signed by:  {peer_id}")
    print(f"  It offers (surplus):       {cbody.get('surplus')}")
    print(f"  It needs (needs):          {cbody.get('needs')}")

    banner("2. Encounter: you send your card; it matches + cost-evaluates, returns a proposal (§8.4)")
    proposal = client.encounter(endpoint, me.signed_card())
    pbody = verify(proposal)
    if pbody.get("type") != "proposal":
        print(f"  It decided to PASS (no viable match): type={pbody.get('type')!r}")
        print("  Edit your needs/surplus above to complement what it offers/needs, then re-run.")
        return 0
    pid = pbody["proposal_id"]
    print(f"  Signed proposal {pid[:8]}...  items:")
    for it in pbody["items"]:
        print(f"    [{it['direction']:<7}] {it['capability']}  "
              f"conf={it['match_confidence']:.2f}  mag={it['magnitude']:g}")

    banner("3. Respond with YOUR OWN cost model + trust — in-process, no server needed (§8.3)")
    resp = me.handle_respond(proposal)          # you decide locally; nothing leaves your machine
    rbody = resp.get("body", {}) if isinstance(resp, dict) else {}
    print(f"  Your decision:  {str(rbody.get('decision', '?')).upper()}   ({rbody.get('reason', '')})")

    banner("4. Close it: bilateral signed outcome — you sign, it counter-signs (§4.3)")
    my_att = make_attestation(me.identity, pid, peer_id, Verdict.FULFILLED)
    counter = client.outcome(endpoint, my_att.to_dict())
    verdict = verify(counter, require_fresh=False).get("verdict")
    print(f"  You signed:          fulfilled")
    print(f"  It counter-signed:   {verdict}   (signed by {counter.get('agent_id', '?')[:24]}...)")

    banner("5. Your portable reputation receipt — verify it anywhere, no permission")
    print("  Keep this signed attestation:")
    print("  " + json.dumps(counter, indent=2).replace("\n", "\n  ")[:1000])
    print("\n  Verify it yourself in three lines:")
    print("      from flp import verify, Envelope")
    print("      body = verify(Envelope.from_dict(attestation))   # raises if tampered")
    print("      assert body['verdict'] == 'fulfilled'")

    ok = True
    try:
        verify(Envelope.from_dict(counter), require_fresh=False)
    except FLPVerifyError:
        ok = False
    print(f"\n  Signature verifies here: {ok}   (flip one byte in the JSON and it fails)")

    print("\n" + "=" * 72)
    print("You just cooperated with a stranger over the open internet — signed,")
    print("verifiable, no registry, no shared operator. That is FLP.")
    print("Honest note: this certifies a completed FLP exchange, not delivered work.")
    return 0


if __name__ == "__main__":
    ep = (sys.argv[1] if len(sys.argv) > 1
          else os.environ.get("FLP_ENDPOINT", DEFAULT_ENDPOINT))
    raise SystemExit(main(ep))
