"""
FLP v1.0 — Matching demo (PROTOCOL.md §6)

Two things:
  1. The three matching layers (exact / vocab synonym / local semantic).
  2. Redemption of v0.1's broken flagship demo: the original
     "VexHermes meets Cabo Intelligence" printed PASS because the two
     agents shared no identical strings. With namespaced URIs + a forkable
     vocabulary, they now match — and the cost model turns that match into
     a real cooperate/pass decision driven by trust.

Run: python demo/demo_matching.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flp.matching import Matcher, Vocabulary  # noqa: E402
from flp.cost_model import CostModel, CapabilityProfile  # noqa: E402


def main():
    print("=" * 72)
    print("FLP v1.0 — Matching (§6): three layers, then v0.1's demo redeemed")
    print("=" * 72)

    m = Matcher(
        vocab=Vocabulary.core(),
        # a toy local semantic matcher (opt-in, advisory, capped at 0.5)
        semantic=lambda a, b: 0.9 if ("scrap" in a and "harvest" in b) else None,
    )

    print("\nLayer-by-layer confidence between a need and a surplus:\n")
    pairs = [
        ("flp:cap/data/market-research", "flp:cap/data/market-research", "exact URI"),
        ("flp:cap/data/market-research", "flp:cap/data/market-intelligence", "vocab synonym"),
        ("flp:cap/data/scraping", "flp:cap/data/web-harvest", "local semantic"),
        ("flp:cap/data/market-research", "flp:cap/tourism/venue-availability", "unrelated"),
    ]
    for need, surplus, label in pairs:
        c = m.confidence(need, surplus)
        shown = f"{c:.2f}" if c is not None else "no match"
        print(f"  {label:<16} {shown}")

    # ---- v0.1 redemption ---------------------------------------------------
    print("\n" + "-" * 72)
    print("v0.1's flagship demo, rebuilt. Original result: PASS (no string overlap).")
    print("-" * 72)

    vex = {
        "objective": "B2B outreach for the Los Cabos corridor",
        "needs": ["flp:cap/tourism/venue-availability"],
        "surplus": ["flp:cap/data/market-intelligence", "flp:cap/data/lead-gen"],
    }
    cabo = {
        "objective": "Local tourism intelligence for Los Cabos",
        "needs": ["flp:cap/data/market-research"],          # vocab-synonym of vex's surplus
        "surplus": ["flp:cap/tourism/venue-availability"],  # exactly vex's need
    }

    res = m.match_cards(cabo, vex, my_magnitudes={"flp:cap/data/market-research": 6.0})

    print("\nFrom Cabo's side:")
    print("  i_need  (Cabo gets from Vex):")
    for it in res["i_need"]:
        print(f"    - {it.capability}  conf={it.match_confidence:.2f}  mag={it.magnitude:g}")
    print("  i_offer (Cabo gives to Vex):")
    for it in res["i_offer"]:
        print(f"    - {it.capability}  conf={it.match_confidence:.2f}")

    if not res["i_need"] and not res["i_offer"]:
        print("  (no match)")
    else:
        print("\n  v0.1 printed PASS here. v1.0 finds a two-sided, reciprocal match.")

    # ---- match -> cost decision -------------------------------------------
    print("\n" + "-" * 72)
    print("Match opens the door; the cost model (with trust) decides to walk through.")
    print("-" * 72)

    cm = CostModel(CapabilityProfile(
        solo_cost={"flp:cap/data/market-research": 8.0}, transport_cost=1.0))

    for label, trust in [("as a stranger (trust 0.0)", 0.0),
                         ("as a proven partner (trust 0.9)", 0.9)]:
        print(f"\n  Cabo evaluating its i_need, {label}:")
        for d in cm.evaluate(res["i_need"], trust=trust):
            verb = "COOPERATE" if d.cooperate else "pass"
            print(f"    {d.capability}: {verb}  "
                  f"(coop_cost={d.coop_cost:.2f} vs solo={d.solo_cost:.0f}, "
                  f"eff_risk={d.effective_risk:.2f} from conf={d.match_confidence:.2f})")

    print("\n  Note: the vocab-synonym match (conf 0.80) raises effective risk, so")
    print("  Cabo is rightly more cautious than on an exact match — §6.7 at work.")

    print("\n" + "=" * 72)
    print("Four pillars stand: identity (§2), reputation (§4), cost (§5), matching (§6).")
    print("Remaining for a live round-trip between two processes: reference server (§8).")


if __name__ == "__main__":
    main()
