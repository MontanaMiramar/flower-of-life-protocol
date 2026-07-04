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

import random
import time

from flp import (
    Identity, FLPAgent, FLPServer, FLPClient, verify,
    Matcher, Vocabulary, CapabilityProfile, CostModel, MatchedItem,
    ReputationLedger, Cooperation, Verdict, make_attestation,
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




# ============================================================================
# Inflated-claim experiment (manifest spec §8.5; closes the loop with §6.7).
#
# Two providers face the IDENTICAL sequence of cooperation opportunities —
# same seed, same counterparties, same magnitudes — so any difference in
# cumulative profit is attributable to strategy alone. The honest provider
# delivers what it announces; the liar announces a capability it does not
# have, accepts, fails, and disputes the outcome (signs "fulfilled" against
# the victim's "failed" — a disagreement is CONFIRMED_BAD either way, §4.3).
#
# Both the liar's private profit and each deceived victim's loss are
# recorded: the social cost of the lie is data, not a footnote.
#
# Run: python stranger_harness.py --inflated-claim
# ============================================================================

EXP_CAPABILITY = "flp:cap/data/market-research"
EXP_MAGNITUDES = (2.0, 10.0, 20.0)   # small always clears at trust 0 (§5.4);
                                     # 10 needs trust > 1/3; 20 needs > 0.72 (§11.1)
EXP_SOLO_COST = 8.0
EXP_TRANSPORT = 1.0
# Experiment accounting, per unit of magnitude. PRICE is paid on acceptance
# (v1 has no settlement layer); DELIVERY is the honest provider's cost of
# actually doing the work; VALUE is what a fulfilled exchange is worth to
# the victim. Lying is locally TEMPTING by construction: pocketing PRICE
# beats PRICE − DELIVERY on any single accepted trial.
EXP_PRICE = 0.5
EXP_DELIVERY = 0.2
EXP_VALUE = 1.2


def _run_strategy(honest, schedule, n_victims, now):
    provider = Identity.generate()
    victims = [Identity.generate() for _ in range(n_victims)]
    ledgers = [ReputationLedger(v.agent_id) for v in victims]
    model = CostModel(CapabilityProfile(
        solo_cost={EXP_CAPABILITY: EXP_SOLO_COST}, transport_cost=EXP_TRANSPORT))

    profit = 0.0          # provider's cumulative take
    victim_net = 0.0      # counterparties' cumulative surplus (+) / loss (−)
    accepted_by_mag = {m: 0 for m in EXP_MAGNITUDES}
    rejected = 0
    trajectory = []       # (trial, trust_at_decision, accepted, profit_so_far)

    for i, (vi, mag) in enumerate(schedule):
        trust = ledgers[vi].trust(provider.agent_id, now=now)
        decision = model.evaluate_item(
            MatchedItem(capability=EXP_CAPABILITY, magnitude=mag), trust)
        if not decision.cooperate:
            rejected += 1
            trajectory.append((i, trust, False, profit))
            continue
        accepted_by_mag[mag] += 1

        if honest:
            profit += (EXP_PRICE - EXP_DELIVERY) * mag
            victim_net += (EXP_VALUE - EXP_PRICE) * mag - EXP_TRANSPORT
            v_verdict, p_verdict = Verdict.FULFILLED, Verdict.FULFILLED
        else:
            profit += EXP_PRICE * mag                       # pockets the price
            victim_net -= EXP_PRICE * mag + EXP_TRANSPORT   # paid, got nothing
            v_verdict, p_verdict = Verdict.FAILED, Verdict.FULFILLED  # disputed

        pid = f"trial-{i}"
        coop = Cooperation(pid, victims[vi].agent_id, provider.agent_id,
                           started_at=now - 60)
        coop.add_attestation(make_attestation(
            victims[vi], pid, provider.agent_id, v_verdict, issued_at=int(now)))
        coop.add_attestation(make_attestation(
            provider, pid, victims[vi].agent_id, p_verdict, issued_at=int(now)))
        ledgers[vi].record(coop)
        trajectory.append((i, trust, True, profit))

    return {
        "provider_profit": round(profit, 2),
        "victim_net": round(victim_net, 2),
        "accepted_by_magnitude": {str(m): n for m, n in accepted_by_mag.items()},
        "rejected": rejected,
        "final_trust_per_victim": [
            round(ledgers[vi].trust(provider.agent_id, now=now), 3)
            for vi in range(n_victims)
        ],
        "trajectory": trajectory,
    }


def run_inflated_claim_experiment(n_trials=50, seed=42, n_victims=3):
    """Honest vs. liar over the identical opportunity schedule. Returns both
    ledgers of numbers; the caller decides what to print or assert."""
    rng = random.Random(seed)
    schedule = [(rng.randrange(n_victims), rng.choice(EXP_MAGNITUDES))
                for _ in range(n_trials)]
    now = time.time()
    return {
        "n_trials": n_trials,
        "seed": seed,
        "n_victims": n_victims,
        "honest": _run_strategy(True, schedule, n_victims, now),
        "liar": _run_strategy(False, schedule, n_victims, now),
    }


def print_inflated_claim_report(res):
    h, l = res["honest"], res["liar"]
    print(f"Inflated-claim experiment — {res['n_trials']} trials, "
          f"{res['n_victims']} counterparties, seed {res['seed']}")
    print(f"{'':22}{'honest':>10}{'liar':>10}")
    print(f"{'provider profit':22}{h['provider_profit']:>10}{l['provider_profit']:>10}")
    print(f"{'victims net':22}{h['victim_net']:>10}{l['victim_net']:>10}")
    for m in EXP_MAGNITUDES:
        key = str(m)
        print(f"{'accepted @ mag ' + key:22}"
              f"{h['accepted_by_magnitude'][key]:>10}{l['accepted_by_magnitude'][key]:>10}")
    print(f"{'rejected':22}{h['rejected']:>10}{l['rejected']:>10}")
    print(f"{'final trust':22}{str(h['final_trust_per_victim']):>10}"
          f"{str(l['final_trust_per_victim']):>10}")
    verdict = "STRICTLY LESS profitable" if l["provider_profit"] < h["provider_profit"] \
        else "NOT less profitable (unexpected!)"
    print(f"-> lying is {verdict}; social cost inflicted: {-l['victim_net']}")


if __name__ == "__main__":
    if "--inflated-claim" in sys.argv:
        print_inflated_claim_report(run_inflated_claim_experiment())
    else:
        main()
