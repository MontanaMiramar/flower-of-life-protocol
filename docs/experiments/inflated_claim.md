# Experiment: The Inflated Claim Is Strictly Unprofitable

*Status: reproducible experiment, feeding §5 of the companion paper.*
*Code: `stranger_harness.py` (`--inflated-claim`) · pinned by `tests/test_inflated_claim.py`.*
*Reproduce: `python stranger_harness.py --inflated-claim` (n=50, seed=42).*

## Question

Manifest spec §8.5, closing the loop with PROTOCOL.md §6.7: an agent whose
`provides` overstates its real capability accepts a cooperation, fails it,
and loses reputation with the counterparty. Is the lying strategy **strictly
less profitable** than honesty across repeated trials — not by assumption,
but in the implemented mechanism's own arithmetic?

## Design

Two providers face the **identical sequence** of 50 cooperation
opportunities — same seed, same three counterparties, same magnitudes — so
the difference in cumulative profit is attributable to strategy alone.

- Magnitudes are drawn from {2, 10, 20}: per §11.1, magnitude 2 clears T\*
  at trust 0 (the probation tier), 10 requires trust > 1/3, 20 requires
  trust > 0.72. Counterparties decide with the reference cost model
  (`solo_cost = 8`, `transport = 1`) and their own relational ledger.
- Accounting per unit of magnitude: price 0.5 paid on acceptance, honest
  delivery cost 0.2, fulfilled value to the counterparty 1.2. Lying is
  therefore **locally tempting by construction**: pocketing 0.5·L beats the
  honest 0.3·L on any single accepted trial.
- The honest provider delivers (both sign `fulfilled`). The liar cannot
  deliver and *disputes* the outcome — it signs `fulfilled` against the
  victim's `failed`. Per §4.3 a disagreement is CONFIRMED-BAD anyway:
  disputing buys the liar nothing.
- Each counterparty's loss is recorded per trial: the social cost of the
  lie is data, not a footnote.
- No testimony propagation between counterparties is enabled (each ledger
  is direct-experience only). This is the *conservative* setting: positive
  testimony would compound the honest provider's advantage.

## Results (n = 50, seed = 42)

|                        | honest | liar  |
|------------------------|-------:|------:|
| provider profit        |  87.0  | 20.0  |
| counterparties net     | +163.0 | −40.0 |
| accepted @ magnitude 2 |    20  |   20  |
| accepted @ magnitude 10|    15  |    0  |
| accepted @ magnitude 20|     5  |    0  |
| rejected               |    10  |   30  |
| final trust (3 victims)| 0.91 / 0.91 / 0.96 | 0 / 0 / 0 |

Honesty out-earns lying **4.35×** despite lying paying more per accepted
trial. Robust across seeds (1, 2, 3, 7, 123 → ratios 2.5–4.5×, liar always
strictly behind, victims always net negative; pinned in
`tests/test_inflated_claim.py`).

## Reading the result: the floor at zero is the mechanism, not a bug

The liar's trust never goes *negative* — `trust(v→liar)` is pinned at the
newcomer floor of 0.0, the same value a blank stranger gets. This is not a
soft spot in the reputation math. It is §4.5.1 carried to its consequence:
**silence punishes — the only negative signal that travels is the absence
of praise.** In Axelrod's terms, FLP's punishment mechanism is the shadow
of the future: the network does not deduct points from a liar, it withdraws
the future cooperations that no longer clear T\*.

Concretely, in the table above: the honest provider converts early
small-magnitude cooperations into trust, and trust into access — 15
mid-magnitude and 5 large-magnitude cooperations the liar never sees. The
liar is not marked; it is **capped**. It remains stuck at the probation
tier where every exchange is small by construction, while carrying an
evidence deficit (one CONFIRMED-BAD = 6× the mass of a good outcome, §4)
that any future honesty must amortize before trust moves at all.

Two honest observations that belong in the paper alongside the headline:

1. **Bounded bleed at the probation tier.** Because known-bad and unknown
   both sit at trust 0, counterparties keep accepting *small* asks from a
   repeat liar (20 of 20 here), losing `price·L + transport` each time. The
   per-trial loss is exactly what the probation cap bounds — that is what
   the cap is *for* — but the cumulative social cost is linear in trials
   (−40 over 50 here). Identifying a repeat offender faster than the floor
   allows is what direct edge memory in an *implementation policy* (e.g.
   refuse after k direct CONFIRMED-BADs) can add on top of the protocol;
   the protocol itself keeps the decision purely in the cost model.
2. **Disputing is free but worthless.** The liar signing `fulfilled`
   against the victim's `failed` neither helps it (disagreement is
   CONFIRMED-BAD, §4.3) nor hurts the victim (negatives are edge-local,
   §4.5.1). The strategic dead end is by design.
