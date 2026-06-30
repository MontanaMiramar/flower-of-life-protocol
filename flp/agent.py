"""
Flower of Life Protocol v1.0 — Agent (PROTOCOL.md §8 endpoint logic)

Framework-agnostic agent that ties the four pillars together and implements the
handlers behind the §8.4 endpoints:

    GET  /.well-known/flp-card   -> signed_card()
    POST /flp/encounter          -> handle_encounter()
    POST /flp/respond            -> handle_respond()
    POST /flp/outcome            -> handle_outcome()
    GET  /flp/status             -> status()

Two v0.1 defects fixed here:
  * Tolerant deserialization (§8.2): unknown fields ignored, never a TypeError.
  * Principled responder (§8.3): the responder evaluates with ITS OWN cost model
    and ITS OWN trust in the proposer — not v0.1's fabricated card with a
    hardcoded "low" cost. `counter` is real: if full magnitude fails but a
    smaller one clears, it counters at the safe magnitude.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .identity import Identity, Envelope, verify, FLPVerifyError, NonceCache, FLP_VERSION
from .reputation import ReputationLedger, Cooperation, Verdict, make_attestation
from .cost_model import CostModel, CapabilityProfile, MatchedItem
from .matching import Matcher, Vocabulary

_KNOWN_CARD_FIELDS = {
    "type", "agent_id", "objective", "needs", "surplus", "vocab",
    "endpoint", "language", "tags", "settlement_type", "issued_at",
    "expires_at", "nonce",
}


def tolerant(data: dict[str, Any], known: set[str]) -> dict[str, Any]:
    """§8.2: keep known fields, silently drop the rest. Never raise on extras."""
    return {k: v for k, v in data.items() if k in known}


@dataclass
class FLPAgent:
    identity: Identity
    objective: str = ""
    needs: list[str] = field(default_factory=list)
    surplus: list[str] = field(default_factory=list)
    endpoint: str = ""
    profile: CapabilityProfile = field(default_factory=CapabilityProfile)
    matcher: Matcher = field(default_factory=lambda: Matcher(vocab=Vocabulary.core()))
    magnitudes: dict[str, float] = field(default_factory=dict)
    settlement_type: str = "digital"

    def __post_init__(self):
        self.cost = CostModel(self.profile)
        self.ledger = ReputationLedger(self.identity.agent_id)
        self.nonces = NonceCache()
        self._coops: dict[str, Cooperation] = {}     # proposal_id -> Cooperation
        self._stats = {"encounters": 0, "proposals": 0, "accepted": 0}

    # -- card ---------------------------------------------------------------- #

    def card_body(self) -> dict[str, Any]:
        return {
            "type": "card",
            "agent_id": self.identity.agent_id,
            "objective": self.objective,
            "needs": list(self.needs),
            "surplus": list(self.surplus),
            "vocab": [self.matcher.vocab.version] if self.matcher.vocab else [],
            "endpoint": self.endpoint,
            "settlement_type": self.settlement_type,
            "expires_at": 9_999_999_999,
        }

    def signed_card(self) -> dict[str, Any]:
        return self.identity.sign(self.card_body()).to_dict()

    # -- /flp/encounter ------------------------------------------------------ #

    def handle_encounter(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Receive a peer's signed card; match + cost-evaluate; maybe propose."""
        body = verify(envelope, nonce_cache=self.nonces)          # §8.1
        their = tolerant(body, _KNOWN_CARD_FIELDS)
        their_id = their.get("agent_id")
        self._stats["encounters"] += 1

        my_card = {"needs": self.needs, "surplus": self.surplus}
        matched = self.matcher.match_cards(my_card, their, my_magnitudes=self.magnitudes)

        trust = self.ledger.trust(their_id)
        cleared = self.cost.proposal_items(matched["i_need"], trust=trust)
        if not cleared and not matched["i_offer"]:
            return self.identity.sign({"type": "response", "decision": "pass"}).to_dict()

        proposal_id = str(uuid.uuid4())
        items = [_item_to_wire(d.capability, "i_need", d.magnitude, d.match_confidence)
                 for d in cleared]
        items += [_item_to_wire(it.capability, "i_offer", it.magnitude, it.match_confidence)
                  for it in matched["i_offer"]]

        # Register the (pending) cooperation so outcomes can later close it.
        self._coops[proposal_id] = Cooperation(
            proposal_id, self.identity.agent_id, their_id,
            started_at=_now(),
        )
        self._stats["proposals"] += 1
        return self.identity.sign({
            "type": "proposal",
            "proposal_id": proposal_id,
            "to_agent": their_id,
            "items": items,
        }).to_dict()

    # -- /flp/respond -------------------------------------------------------- #

    def handle_respond(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Receive a proposal; decide with MY cost model + MY trust (§8.3)."""
        body = verify(envelope, nonce_cache=self.nonces)
        proposer = envelope["agent_id"] if isinstance(envelope, dict) else envelope.agent_id
        proposal_id = body.get("proposal_id")
        trust = self.ledger.trust(proposer)

        # I evaluate what I would RECEIVE: the proposer's i_need are things they
        # take from me (my outflow, cheap); their i_offer are things I receive.
        incoming = [it for it in body.get("items", []) if it.get("direction") == "i_offer"]

        decisions, counters = [], []
        for it in incoming:
            mi = MatchedItem(it["capability"], "i_need",
                             magnitude=float(it.get("magnitude", 1.0)),
                             match_confidence=float(it.get("match_confidence", 1.0)))
            d = self.cost.evaluate_item(mi, trust=trust)
            if d.cooperate:
                decisions.append(True)
            else:
                safe = self.cost.max_safe_magnitude(
                    mi.capability, trust, mi.match_confidence)
                if safe > 0:
                    counters.append(_item_to_wire(
                        mi.capability, "i_offer", round(safe, 3), mi.match_confidence))
                    decisions.append("counter")
                else:
                    decisions.append(False)

        if incoming and all(d is True for d in decisions):
            decision, counter_items = "accept", None
            self._stats["accepted"] += 1
        elif any(d == "counter" for d in decisions):
            decision, counter_items = "counter", counters
        else:
            decision, counter_items = "decline", None

        # Mirror the cooperation locally so this side can also close it later.
        if proposal_id and proposal_id not in self._coops and decision != "decline":
            self._coops[proposal_id] = Cooperation(
                proposal_id, proposer, self.identity.agent_id, started_at=_now())

        return self.identity.sign({
            "type": "response",
            "proposal_id": proposal_id,
            "decision": decision,
            "counter_items": counter_items,
            "reason": f"trust={trust:.2f}",
        }).to_dict()

    # -- /flp/outcome -------------------------------------------------------- #

    def handle_outcome(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Record the peer's signed attestation; counter-sign ours (§4.3)."""
        env = Envelope.from_dict(envelope) if isinstance(envelope, dict) else envelope
        body = verify(env, require_fresh=False)
        proposal_id = body.get("proposal_id")
        coop = self._coops.get(proposal_id)
        if coop is None:
            raise FLPVerifyError("validation_failed", "unknown proposal_id")
        coop.add_attestation(env)                                  # their verdict
        # Counter-sign our matching verdict (reference: we report fulfilled).
        ours = make_attestation(self.identity, proposal_id,
                                body.get("counterparty", env.agent_id),
                                Verdict.FULFILLED)
        coop.add_attestation(ours)
        self.ledger.record(coop)
        return ours.to_dict()

    # -- /flp/status --------------------------------------------------------- #

    def status(self) -> dict[str, Any]:
        return {
            "type": "status",
            "agent_id": self.identity.agent_id,
            "flp_version": FLP_VERSION,
            "vocab": [self.matcher.vocab.version] if self.matcher.vocab else [],
            **self._stats,
        }


def _item_to_wire(capability, direction, magnitude, match_confidence):
    return {
        "capability": capability,
        "direction": direction,
        "magnitude": magnitude,
        "match_confidence": match_confidence,
    }


def _now() -> float:
    import time
    return time.time()
