"""
FLP v1.0 — Cost Model Calibration Guide (PROTOCOL.md §5)

The cost model is what makes FLP real: cooperation only happens when it's
cheaper than doing it alone. This demo shows how to calibrate the parameters
so the model makes sensible decisions for YOUR agent.

Key parameters
--------------
  solo_cost        How much it costs your agent to get this capability on its own.
                   Think: hours of work, API calls, compute, risk of bad results.
                   Use relative numbers that make sense for your domain.

  transport_cost   Fixed overhead per cooperation: latency, key exchange,
                   coordination effort. Usually 0.5-2.0.

  trust            In [0,1]. A brand-new stranger = 0.0. After 10 successful
                   cooperations with no disputes = ~0.9. Reputation is earned.

How the model decides
---------------------
  coop_cost  = (1 - match_confidence) * solo_cost * effective_risk + transport_cost
  effective_risk = 1.0 + (1 - trust) * risk_premium
  cooperate  = (coop_cost < solo_cost)

  Intuition: if the match is uncertain (low confidence) and the stranger is
  unknown (low trust), the effective cost of trusting them rises. You still
  cooperate when the solo_cost is high enough to make even an uncertain
  cooperation worthwhile.

Run: python3 demo/demo_cost_calibration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_v1_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_v1_path))

from flp import CostModel, CapabilityProfile, MatchedItem


def show(label: str, profile: CapabilityProfile, item: MatchedItem,
         trusts: list[float]):
    cm = CostModel(profile)
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"  capability : {item.capability.split('/')[-1]}")
    print(f"  solo_cost  : {profile.solo_cost.get(item.capability, '?')}")
    print(f"  confidence : {item.match_confidence:.2f}")
    print(f"{'─'*60}")
    print(f"  {'trust':>8}  {'coop_cost':>10}  {'eff_risk':>9}  decision")
    for trust in trusts:
        d = cm.evaluate_item(item, trust=trust)
        tag = "COOPERATE ✓" if d.cooperate else "pass ✗"
        print(f"  {trust:>8.1f}  {d.coop_cost:>10.2f}  {d.effective_risk:>9.2f}  {tag}")


def main():
    print("FLP v1.0 — Cost Model Calibration Examples")
    print("=" * 60)

    # ── Example 1: High solo_cost (data you can't easily get yourself) ──────
    # Vex needs local tourism data. Getting it yourself = scraping + cleaning
    # = hours of work. solo_cost = 9.0 (high). Even a low-confidence match
    # from a stranger is worth trying.
    show(
        "HIGH solo_cost: tourism data (hard to get alone)",
        CapabilityProfile(
            solo_cost={"flp:cap/tourism/local-venue-data": 9.0},
            transport_cost=1.0,
        ),
        MatchedItem(
            capability="flp:cap/tourism/local-venue-data",
            direction="i_need",
            magnitude=1.0,
            match_confidence=0.34,  # Layer 3 semantic match
        ),
        trusts=[0.0, 0.3, 0.6, 0.9],
    )

    # ── Example 2: Low solo_cost (data you can easily get yourself) ─────────
    # If Vex can scrape the same data in 5 minutes, solo_cost = 2.0.
    # Now even a high-confidence stranger isn't worth the transport overhead.
    show(
        "LOW solo_cost: data you can easily get yourself",
        CapabilityProfile(
            solo_cost={"flp:cap/tourism/local-venue-data": 2.0},
            transport_cost=1.0,
        ),
        MatchedItem(
            capability="flp:cap/tourism/local-venue-data",
            direction="i_need",
            magnitude=1.0,
            match_confidence=0.80,  # Layer 2 synonym match
        ),
        trusts=[0.0, 0.5, 0.9],
    )

    # ── Example 3: Layer 2 vs Layer 3 confidence at zero trust ─────────────
    # Same scenario, different match quality. Shows why Layer 2 (0.80)
    # cooperates where Layer 3 (0.34) might not, depending on solo_cost.
    print("\n" + "=" * 60)
    print("LAYER 2 vs LAYER 3 — same capability, same stranger (trust=0.0)")
    print("=" * 60)
    profile = CapabilityProfile(
        solo_cost={"flp:cap/data/market-research": 6.0},
        transport_cost=1.0,
    )
    cm = CostModel(profile)
    for conf, layer in [(1.00, "L1 exact"), (0.80, "L2 synonym"),
                         (0.50, "L3 semantic"), (0.34, "L3 low")]:
        item = MatchedItem(
            capability="flp:cap/data/market-research",
            direction="i_need",
            magnitude=1.0,
            match_confidence=conf,
        )
        d   = cm.evaluate_item(item, trust=0.0)
        tag = "COOPERATE ✓" if d.cooperate else "pass ✗"
        print(f"  {layer:12s}  conf={conf:.2f}  coop_cost={d.coop_cost:.2f}  {tag}")

    # ── Calibration worksheet ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("CALIBRATION WORKSHEET")
    print("=" * 60)
    print("""
For each capability your agent needs, ask:

  1. How much does it cost to get this on my own?
     (compute, time, API calls, quality risk)
     → Set solo_cost to a number that reflects this.
       A rough scale: trivial=1, moderate=4, expensive=8, impossible=12

  2. How much overhead does one FLP cooperation add?
     (network, key exchange, waiting for response)
     → Set transport_cost. Typically 0.5-1.5.

  3. What's the minimum trust level I'll accept for first contact?
     → The cost model handles this automatically. At trust=0.0 the
        effective_risk is highest; the model will only cooperate if
        solo_cost is high enough to absorb the risk premium.

Rule of thumb: if you'd rather cooperate than go alone even with a
stranger, solo_cost should be >= 2 * transport_cost / (1 - confidence).
""")


if __name__ == "__main__":
    main()
