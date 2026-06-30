"""
FLP v1.0 — Stranger harness: divergent-vocabulary field test (PROTOCOL.md §6)

Purpose
-------
Validate the ONE thing a real stranger reveals that a copy-paste demo cannot:
whether the protocol reconciles vocabulary an outside party chose WITHOUT
coordinating with you. The mechanics (identity, reputation, cost, handshake)
are already covered by the test suite; this harness stresses Layer 1/2/3
MATCHING under honest divergence, end to end over real HTTP.

Methodological honesty (read this before trusting the result)
-------------------------------------------------------------
The "stranger" agent below MUST declare capabilities the way an outside Los
Cabos business would phrase them — NOT copied from your core.json. If you write
the stranger's vocabulary while looking at your own vocabulary, you prove
nothing. The three tiers are designed so that SOME must match and one must
*fail* — a failure at Tier 2 is a CORRECT result that maps the edge of your
core vocabulary, not a bug.

Run: python stranger_harness.py
"""

import sys
from pathlib import Path

# Works whether FLP is pip-installed or run from a clone.
try:
    import flp  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from flp import (
    Identity, FLPAgent, FLPServer, FLPClient, verify,
    Matcher, Vocabulary, CapabilityProfile, CostModel, MatchedItem,
)

# ============================================================================
# YOUR side: an agent built on YOUR core vocabulary.
# ============================================================================
def build_home_agent():
    return FLPAgent(
        identity=Identity.generate(),
        objective="Local tourism intelligence, Los Cabos",
        needs=["flp:cap/data/market-research"],
        surplus=["flp:cap/tourism/venue-availability"],
        endpoint="https://home.example",
        profile=CapabilityProfile(
            solo_cost={"flp:cap/data/market-research": 8.0}, transport_cost=1.0),
    )

# ============================================================================
# STRANGER side — DECLARE THIS WITHOUT LOOKING AT core.json.
# Phrase capabilities the way an outside business naturally would. The whole
# point is that this vocabulary DIVERGED from yours. Edit freely and re-run.
# ============================================================================
STRANGER_TIERS = {
    # Tier 1: a core-vocabulary SYNONYM (in core.json, but not the canonical term).
    #         Expectation: MATCH at confidence 0.80 (Layer 2).
    "tier1_core_synonym": {
        "needs": ["flp:cap/tourism/venue-availability"],
        "surplus": ["flp:cap/data/market-intelligence"],
    },
    # Tier 2: foreign-but-close phrasing NOT in core.json.
    #         Expectation WITHOUT semantic layer: NO MATCH (correct! maps the edge).
    "tier2_foreign_vocab": {
        "needs": ["flp:cap/tourism/venue-availability"],
        "surplus": ["flp:cap/data/competitor-scraping"],
    },
    # Tier 3: same foreign phrasing, evaluated WITH a local semantic matcher.
    #         Expectation: MATCH at confidence <= 0.50, and cost model more cautious.
    "tier3_semantic": {
        "needs": ["flp:cap/tourism/venue-availability"],
        "surplus": ["flp:cap/data/competitor-scraping"],
    },
}


def naive_semantic(a: str, b: str):
    """A deliberately simple LOCAL semantic matcher (Layer 3, opt-in).

    Replace with a real local-embedding / local-LLM call against your own model.
    Returns a confidence in [0,1] or None. Kept crude on purpose so the test is
    legible; the protocol caps whatever it returns at 0.50 (advisory).
    """
    market_terms = {"market-research", "market-intelligence", "competitor-scraping",
                    "competitor-analysis", "lead-gen"}
    a_leaf = a.rsplit("/", 1)[-1]
    b_leaf = b.rsplit("/", 1)[-1]
    if a_leaf in market_terms and b_leaf in market_terms:
        return 0.85
    return None


def run_tier(name, stranger_card, *, semantic=None):
    home = build_home_agent()
    matcher = Matcher(vocab=Vocabulary.core(), semantic=semantic)

    # Home evaluates what it would RECEIVE from the stranger (its i_need).
    matched = matcher.match_cards(
        {"needs": home.needs, "surplus": home.surplus}, stranger_card)
    cm = CostModel(home.profile)

    print(f"\n=== {name} ===")
    print(f"  stranger surplus: {stranger_card['surplus']}")
    i_need = matched["i_need"]
    if not i_need:
        print("  MATCH: none  (Layer 1/2/3 found no bridge to home's needs)")
    for it in i_need:
        # decide at stranger trust = 0 (true first contact) and at a proven 0.9
        d0 = cm.evaluate_item(it, trust=0.0)
        d9 = cm.evaluate_item(it, trust=0.9)
        print(f"  MATCH: {it.capability}  confidence={it.match_confidence:.2f}")
        print(f"    stranger (trust 0.0): {'COOPERATE' if d0.cooperate else 'pass'}"
              f"  (coop_cost={d0.coop_cost:.2f} vs solo={d0.solo_cost:.0f},"
              f" eff_risk={d0.effective_risk:.2f})")
        print(f"    proven   (trust 0.9): {'COOPERATE' if d9.cooperate else 'pass'}"
              f"  (coop_cost={d9.coop_cost:.2f})")
    return i_need


def main():
    print("=" * 72)
    print("FLP v1.0 — Stranger harness: divergent-vocabulary field test")
    print("=" * 72)
    print("Reminder: Tier 2 SHOULD report 'no match'. That is a correct result —")
    print("it maps the edge of your core vocabulary, not a failure.")

    t1 = run_tier("Tier 1 — core synonym (expect MATCH @0.80)",
                  STRANGER_TIERS["tier1_core_synonym"])
    t2 = run_tier("Tier 2 — foreign vocab, NO semantic (expect NO MATCH)",
                  STRANGER_TIERS["tier2_foreign_vocab"])
    t3 = run_tier("Tier 3 — foreign vocab, WITH local semantic (expect MATCH <=0.50)",
                  STRANGER_TIERS["tier3_semantic"], semantic=naive_semantic)

    # --- live HTTP round-trip with the Tier-1 stranger, full cycle ----------
    print("\n" + "=" * 72)
    print("Live HTTP round-trip against the Tier-1 stranger (full mechanics)")
    print("=" * 72)
    home = build_home_agent()
    stranger = FLPAgent(
        identity=Identity.generate(),
        objective="(outside business)",
        needs=STRANGER_TIERS["tier1_core_synonym"]["needs"],
        surplus=STRANGER_TIERS["tier1_core_synonym"]["surplus"],
        endpoint="https://stranger.example",
        profile=CapabilityProfile(
            solo_cost={"flp:cap/tourism/venue-availability": 8.0}, transport_cost=1.0),
    )
    sv_home = FLPServer(home).start()
    sv_stranger = FLPServer(stranger).start()
    client = FLPClient(allow_private=True)   # loopback dev only
    try:
        card = client.fetch_card(sv_stranger.base_url)
        print(f"  discovered + verified stranger: {verify(card)['agent_id'][:24]}...")
        proposal = client.encounter(sv_stranger.base_url, home.signed_card())
        pbody = verify(proposal)
        print(f"  proposal type: {pbody['type']}, items: "
              f"{[(i['capability'].split('/')[-1], i['direction']) for i in pbody.get('items', [])]}")
        response = client.respond(sv_home.base_url, proposal)
        print(f"  home's decision: {verify(response)['decision'].upper()}")
        print("  --> a stranger with vocabulary you didn't write completed the handshake.")
    finally:
        sv_home.stop()
        sv_stranger.stop()


if __name__ == "__main__":
    main()
