"""
FLP v1.0 — Live round-trip demo (PROTOCOL.md §8)

Two independent agents, each behind its own HTTP server, complete a full
cooperation over the wire with NO shared setup beyond the protocol itself:

    fetch card -> encounter -> proposal -> response -> outcome -> reputation

Everything is signed and verified end to end. The only thing the two agents
share is FLP. This is what v0.1 never had: a live, runnable handshake.

Run: python demo/demo_roundtrip.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flp.identity import Identity, verify, FLP_VERSION  # noqa: E402
from flp.cost_model import CapabilityProfile  # noqa: E402
from flp.reputation import make_attestation, Verdict  # noqa: E402
from flp.agent import FLPAgent  # noqa: E402
from flp.server import FLPServer, FLPClient  # noqa: E402


def banner(s):
    print("\n" + "-" * 70 + f"\n{s}\n" + "-" * 70)


def main():
    print("=" * 70)
    print("FLP v1.0 — Live HTTP round-trip: two agents, one protocol")
    print("=" * 70)

    # Two agents with complementary needs/surplus.
    cabo = FLPAgent(
        identity=Identity.generate(),
        objective="Local tourism intelligence, Los Cabos",
        needs=["flp:cap/data/market-research"],
        surplus=["flp:cap/tourism/venue-availability"],
        endpoint="https://cabo.example",
        profile=CapabilityProfile(
            solo_cost={"flp:cap/data/market-research": 8.0}, transport_cost=1.0),
        magnitudes={"flp:cap/data/market-research": 3.0},   # a modest first ask
    )
    vex = FLPAgent(
        identity=Identity.generate(),
        objective="B2B outreach, Los Cabos corridor",
        needs=["flp:cap/tourism/venue-availability"],
        surplus=["flp:cap/data/market-intelligence"],       # vocab-synonym of cabo's need
        endpoint="https://vex.example",
        profile=CapabilityProfile(
            solo_cost={"flp:cap/tourism/venue-availability": 8.0}, transport_cost=1.0),
    )

    sv_cabo = FLPServer(cabo).start()
    sv_vex = FLPServer(vex).start()
    # allow_private=True ONLY because this demo runs on loopback. Never in prod.
    client = FLPClient(allow_private=True)

    try:
        print(f"\nCabo @ {sv_cabo.base_url}")
        print(f"Vex  @ {sv_vex.base_url}")

        banner("1. Cabo fetches Vex's card and verifies it (no registry, §2.2/§7.2)")
        vex_card = client.fetch_card(sv_vex.base_url)
        vbody = verify(vex_card)
        print(f"  Verified. Vex offers: {vbody['surplus']}")
        print(f"  Signed by: {vbody['agent_id'][:28]}...")

        banner("2. Cabo encounters Vex; Vex matches + cost-evaluates, returns proposal (§8.4)")
        proposal = client.encounter(sv_vex.base_url, cabo.signed_card())
        pbody = verify(proposal)
        print(f"  Proposal {pbody['proposal_id'][:8]}... with items:")
        for it in pbody["items"]:
            print(f"    [{it['direction']:<7}] {it['capability']}  "
                  f"conf={it['match_confidence']:.2f} mag={it['magnitude']:g}")

        banner("3. Cabo responds using ITS OWN cost model + trust in Vex (§8.3)")
        response = client.respond(sv_cabo.base_url, proposal)
        rbody = verify(response)
        print(f"  Decision: {rbody['decision'].upper()}   ({rbody['reason']})")
        if rbody.get("counter_items"):
            for it in rbody["counter_items"]:
                print(f"    counter: {it['capability']} at safe mag={it['magnitude']:g}")

        banner("4. They close the cooperation: bilateral signed outcome (§4.3)")
        pid = pbody["proposal_id"]
        # Cabo signs its verdict and sends it to Vex's /flp/outcome; Vex counter-signs.
        cabo_att = make_attestation(cabo.identity, pid, vex.identity.agent_id,
                                    Verdict.FULFILLED)
        vex_counter = client.outcome(sv_vex.base_url, cabo_att.to_dict())
        vbody2 = verify(vex_counter, require_fresh=False)
        print(f"  Cabo signed: fulfilled")
        print(f"  Vex counter-signed: {vbody2['verdict']}  -> CONFIRMED_GOOD")

        banner("5. Reputation updates on Vex's side (§4)")
        t_before = 0.0
        t_after = vex.ledger.trust(cabo.identity.agent_id)
        print(f"  Vex's trust in Cabo:  {t_before:.3f}  ->  {t_after:.3f}")
        print(f"  The next exchange between them will clear at larger magnitude.")

        banner("Status introspection (§9.5)")
        st = client.status(sv_vex.base_url)
        print(f"  Vex: flp_version={st['flp_version']}  vocab={st['vocab']}  "
              f"encounters={st['encounters']} proposals={st['proposals']}")

        print("\n" + "=" * 70)
        print("Full signed handshake completed over real HTTP. Five pillars live:")
        print("identity (§2) · reputation (§4) · cost (§5) · matching (§6) · server (§8)")
        print("A stranger can now run this against you and cooperate — safely.")

    finally:
        sv_cabo.stop()
        sv_vex.stop()


if __name__ == "__main__":
    main()
