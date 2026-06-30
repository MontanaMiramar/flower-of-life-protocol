"""
Flower of Life Protocol v1.0 — Cost Model (PROTOCOL.md §5)

The decision layer. Converts relational trust (§4) into a per-capability
cooperate/pass decision:

    coop_cost(c)  = transport_cost + ( effective_risk(c) * magnitude(c) )
    cooperate(c)  <=>  coop_cost(c) < solo_cost(c)

where
    risk(me->X)        = RISK_MAX - trust(me->X) * (RISK_MAX - RISK_MIN)   (§5.3)
    effective_risk(c)  = risk(me->X) / match_confidence(c)                 (§6.7)

Unlike v0.1 (where a fixed cost ceiling below a fixed solo constant made the
comparison always true), here the equation BITES: the trust curve is an
OUTPUT of this model, not an assumption bolted on (§5.4).

solo_cost and magnitude are PRIVATE and per-item; they are never published in
a card (§5.3 / §8.3). Only the structure is normative; the numbers are an
agent's own business (§5.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

# --- reference constants (shape normative, numbers tunable — §5.6) --------- #
RISK_MAX = 1.0
RISK_MIN = 0.1
DEFAULT_TRANSPORT_COST = 1.0
DEFAULT_SOLO_COST = 5.0
DEFAULT_MAGNITUDE = 1.0


def risk(trust: float, risk_max: float = RISK_MAX, risk_min: float = RISK_MIN) -> float:
    """Counterparty risk as a decreasing function of relational trust (§5.3).

    trust = 0 (stranger)      -> risk_max
    trust -> 1 (proven peer)  -> risk_min
    """
    t = min(max(trust, 0.0), 1.0)
    return risk_max - t * (risk_max - risk_min)


@dataclass
class CapabilityProfile:
    """An agent's PRIVATE economics. Never serialized into a card."""
    solo_cost: dict[str, float] = field(default_factory=dict)
    default_solo_cost: float = DEFAULT_SOLO_COST
    transport_cost: float = DEFAULT_TRANSPORT_COST
    risk_max: float = RISK_MAX
    risk_min: float = RISK_MIN

    def solo(self, capability: str) -> float:
        return self.solo_cost.get(capability, self.default_solo_cost)


@dataclass
class ItemDecision:
    """The per-capability verdict for one matched item."""
    capability: str
    direction: str            # "i_need" | "i_offer"
    cooperate: bool
    coop_cost: float
    solo_cost: float
    effective_risk: float
    magnitude: float
    match_confidence: float

    def reason(self) -> str:
        verb = "cooperate" if self.cooperate else "pass"
        return (f"{verb}: coop_cost={self.coop_cost:.2f} "
                f"{'<' if self.cooperate else '>='} solo={self.solo_cost:.2f} "
                f"(risk={self.effective_risk:.2f}, mag={self.magnitude:g}, "
                f"conf={self.match_confidence:g})")


@dataclass
class MatchedItem:
    """A capability the matcher (§6) found in needs ∩ surplus, with stakes."""
    capability: str
    direction: str = "i_need"          # "i_need" | "i_offer"
    magnitude: float = DEFAULT_MAGNITUDE
    match_confidence: float = 1.0      # 1.0 exact, <1 fuzzy (§6.7)


class CostModel:
    """Decides, per capability, whether cooperation beats going solo."""

    def __init__(self, profile: Optional[CapabilityProfile] = None):
        self.profile = profile or CapabilityProfile()

    def evaluate_item(self, item: MatchedItem, trust: float) -> ItemDecision:
        base_risk = risk(trust, self.profile.risk_max, self.profile.risk_min)
        # Lower match confidence inflates effective risk (§6.7): a fuzzy match
        # must clear a higher bar, so it needs smaller stakes or more trust.
        conf = min(max(item.match_confidence, 1e-6), 1.0)
        eff_risk = base_risk / conf
        coop_cost = self.profile.transport_cost + eff_risk * item.magnitude
        solo = self.profile.solo(item.capability)
        return ItemDecision(
            capability=item.capability,
            direction=item.direction,
            cooperate=coop_cost < solo,
            coop_cost=coop_cost,
            solo_cost=solo,
            effective_risk=eff_risk,
            magnitude=item.magnitude,
            match_confidence=item.match_confidence,
        )

    def evaluate(self, items: Iterable[MatchedItem], trust: float) -> list[ItemDecision]:
        """Decide every matched item. One encounter can mix cooperate and pass."""
        return [self.evaluate_item(it, trust) for it in items]

    def proposal_items(self, items: Iterable[MatchedItem], trust: float) -> list[ItemDecision]:
        """Only the items that cleared their own threshold (§5.2).

        These are exactly the items a proposal should carry.
        """
        return [d for d in self.evaluate(items, trust) if d.cooperate]

    def max_safe_magnitude(self, capability: str, trust: float,
                           match_confidence: float = 1.0) -> float:
        """Largest magnitude of `capability` that still clears at this trust.

        The probation tier (§3.3) in closed form: with a stranger (trust 0)
        this is small; with a proven peer it is large. Returns 0 if no
        positive magnitude clears (transport alone already >= solo).
        """
        base_risk = risk(trust, self.profile.risk_max, self.profile.risk_min)
        conf = min(max(match_confidence, 1e-6), 1.0)
        eff_risk = base_risk / conf
        solo = self.profile.solo(capability)
        headroom = solo - self.profile.transport_cost
        if headroom <= 0 or eff_risk <= 0:
            return 0.0 if headroom <= 0 else float("inf")
        return headroom / eff_risk
