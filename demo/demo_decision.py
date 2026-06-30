"""
FLP v1.0 — End-to-end demo: the full decision pipeline (§2 -> §4 -> §5)

The thesis, running as one chain:

    signed identity (§2)  ->  relational trust (§4)  ->  cost decision (§5)

We watch ONE capability, between the SAME two agents, flip from "pass" to
"cooperate (large)" — not because anything was reconfigured, but because
trust was EARNED through signed bilateral outcomes. The equation bites; the
trust curve is the model's output, not an assumption.

Run: python demo/demo_decision.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flp.identity import Identity  # noqa: E402
from flp.reputation import (  # noqa: E402
    ReputationLedger, Cooperation, Verdict, make_attestation,
)
from flp.cost_model import (  # noqa: E402
    CostModel, CapabilityProfile, MatchedItem,
)

NOW = time.time()
CAP = "flp:cap/data/market-research"


def coop(pid, A, B, v=Verdict.FULFILLED):
    c = Cooperation(pid, A.agent_id, B.agent_id, started_at=NOW - 10)
    c.add_attestation(make_attestation(A, pid, B.agent_id, v, issued_at=int(NOW - 5)))
    c.add_attestation(make_attestation(B, pid, A.agent_id, v, issued_at=int(NOW - 5)))
    return c


def main():
    print("=" * 72)
    print("FLP v1.0 — Full pipeline: identity -> reputation -> cost decision")
    print("=" * 72)

    cabo = Identity.generate()     # the deciding agent
    vex = Identity.generate()      # counterparty offering market-research

    led = ReputationLedger(cabo.agent_id)

    # Cabo finds market-research expensive to do alone; this is private to Cabo.
    profile = CapabilityProfile(solo_cost={CAP: 8.0}, transport_cost=1.0)
    cm = CostModel(profile)

    # Cabo always wants a LARGE ongoing feed of market-research (magnitude 10).
    big_ask = MatchedItem(CAP, direction="i_need", magnitude=10, match_confidence=1.0)

    def decide(label):
        t = led.trust(vex.agent_id, now=NOW)
        d = cm.evaluate_item(big_ask, trust=t)
        flag = "COOPERATE" if d.cooperate else "pass     "
        print(f"  {label:<26} trust={t:.3f}  risk={d.effective_risk:.2f}  "
              f"coop_cost={d.coop_cost:5.2f} vs solo={d.solo_cost:.0f}  -> {flag}")

    print(f"\nCabo needs a LARGE feed of {CAP} (magnitude 10).")
    print("Same capability, same counterparty, throughout. Only trust changes.\n")

    decide("stranger")                          # trust 0 -> pass
    for i in range(1, 9):
        led.record(coop(f"job{i}", cabo, vex))  # small successful jobs accrue trust
        decide(f"after {i} good job(s)")

    print("\n  The large feed was REFUSED to a stranger and UNLOCKED for a proven")
    print("  partner — with zero reconfiguration. Trust earned via signed outcomes")
    print("  lowered risk, which lowered coop_cost below what Cabo would spend alone.")

    # And the asymmetry: a single defection re-locks it.
    led.record(coop("betray", cabo, vex, v=Verdict.FAILED))
    print()
    decide("after 1 defection")
    print("\n  One betrayal (weight 6) erased the trust of ~6 good jobs in a single")
    print("  step, knocking trust from 0.80 back to 0.33 -> the large feed re-locks.")
    print("  Cooperation is the path of least resistance ONLY while trust holds;")
    print("  defection is expensive by construction. That asymmetry is now")
    print("  arithmetic you can run, not a slogan.")

    print("\n" + "=" * 72)
    print("Three pillars stand: identity (§2), reputation (§4), cost (§5).")
    print("Remaining for a full round-trip: matching (§6) + reference server (§8).")


if __name__ == "__main__":
    main()
