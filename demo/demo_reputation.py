"""
FLP v1.0 — Reputation layer demo (PROTOCOL.md §4)

Shows the relational trust curve emerging from signed bilateral outcomes:
  1. a stranger starts at zero,
  2. cooperation builds trust sub-linearly,
  3. a single defection craters it (super-linear),
  4. a Sybil clique cannot reach an observer it never transacted with,
  5. trust is relational: two observers compute different values.

Run: python demo/demo_reputation.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flp.identity import Identity  # noqa: E402
from flp.reputation import (  # noqa: E402
    ReputationLedger, Cooperation, Verdict, make_attestation,
)

NOW = time.time()


def coop(pid, A, B, va, vb):
    c = Cooperation(pid, A.agent_id, B.agent_id, started_at=NOW - 10)
    c.add_attestation(make_attestation(A, pid, B.agent_id, va, issued_at=int(NOW - 5)))
    c.add_attestation(make_attestation(B, pid, A.agent_id, vb, issued_at=int(NOW - 5)))
    return c


def bar(t):
    return "#" * int(round(t * 40)) + "-" * (40 - int(round(t * 40)))


def main():
    print("=" * 70)
    print("FLP v1.0 — Relational Reputation (§4): the trust curve emerges")
    print("=" * 70)

    cabo = Identity.generate()        # the observer
    vex = Identity.generate()         # a counterparty Cabo will transact with
    led = ReputationLedger(cabo.agent_id)

    F = Verdict.FULFILLED
    X = Verdict.FAILED

    print(f"\nObserver: Cabo   Counterparty: Vex")
    print(f"\nCabo's trust in Vex, as signed outcomes accumulate:\n")
    print(f"  start (stranger)         {led.trust(vex.agent_id, now=NOW):.3f}  |{bar(led.trust(vex.agent_id, now=NOW))}|")

    for i in range(1, 7):
        led.record(coop(f"good{i}", cabo, vex, F, F))
        t = led.trust(vex.agent_id, now=NOW)
        print(f"  after {i} good exchange(s)  {t:.3f}  |{bar(t)}|")

    print("\n  --> sub-linear: each additional success adds less. Trust is earned slowly.")

    # One defection.
    led.record(coop("defect", cabo, vex, X, X))
    t = led.trust(vex.agent_id, now=NOW)
    print(f"\n  after 1 DEFECTION        {t:.3f}  |{bar(t)}|")
    print("  --> super-linear collapse: one failure outweighs many cooperations.")
    print("      This asymmetry is what makes defection irrational.")

    # Sybil clique.
    print("\n" + "-" * 70)
    print("Sybil clique (§4.5): 6 fresh identities vouch for each other.")
    sybils = [Identity.generate() for _ in range(6)]
    led2 = ReputationLedger(cabo.agent_id)
    for i in range(1, 6):
        led2.record(coop(f"syb{i}", sybils[0], sybils[i], F, F))
    t_syb = led2.trust(sybils[0].agent_id, now=NOW)
    print(f"  Their mutual praise, from Cabo's view:  {t_syb:.3f}")
    print("  --> zero. No trusted path reaches Cabo. Sybil resistance is free,")
    print("      a property of the relational topology, not a counter-measure.")

    # Relational.
    print("\n" + "-" * 70)
    print("Relational (§4.1): same agent, two observers, two truths.")
    alice, bob, target = Identity.generate(), Identity.generate(), Identity.generate()
    shared = coop("at", alice, target, F, F)
    la = ReputationLedger(alice.agent_id); la.record(shared)
    lb = ReputationLedger(bob.agent_id); lb.record(shared)
    print(f"  Alice's trust in target (she worked with them): "
          f"{la.trust(target.agent_id, observer=alice.agent_id, now=NOW):.3f}")
    print(f"  Bob's trust in target   (he never did):         "
          f"{lb.trust(target.agent_id, observer=bob.agent_id, now=NOW):.3f}")
    print("  --> there is no global score to capture. Trust is a viewpoint.")

    print("\n" + "=" * 70)
    print("Two pillars now stand: signed identity (§2) + relational reputation (§4).")
    print("trust(me->X) is ready to feed the §5 cost model — where it makes the")
    print("cooperation decision, and the equation finally bites.")


if __name__ == "__main__":
    main()
