"""
Flower of Life Protocol v1.0 — Relational Reputation (PROTOCOL.md §4)

Implements:
  - Bilateral outcome attestations (§4.3)
  - Terminal states: CONFIRMED_GOOD / CONFIRMED_BAD / DANGLING / PENDING (§4.3-4.4)
  - The dangling penalty: silence is not a refuge (§4.4)
  - trust(me -> X): relational, no global score (§4.1-4.2)
  - Distance decay over the trust graph + Sybil resistance for free (§4.5)
  - Time decay of evidence, half-life 90d (§4.6)

Output: trust(me -> X) in [0, 1], the single input to the §5 cost model (§4.7).

------------------------------------------------------------------------------
DESIGN DECISION (on record) — positives propagate, negatives are edge-local.
The prose spec leaves the §4.3 (anti-defamation) / §4.4 (dangling) / §4.5
(propagation) interaction underspecified. Implemented resolution:

  * CONFIRMED_GOOD (both parties signed `fulfilled`) is forgery-proof and
    PROPAGATES as positive testimony through the trust graph.
  * Negative outcomes (mutual-bad, disputed, dangling) affect ONLY the direct
    edge between the two involved parties. They DO NOT propagate as third-party
    testimony.

Why: if negatives propagated, a defamer Y could broadcast "X failed" that no
one can verify, reopening the very attack §4.3 closes. By making negatives
edge-local, an agent cannot shout negatives about others — it can only WITHHOLD
positive testimony (stop vouching) and stop referring. A known defector's
reputation falls because positive testimony stops flowing toward it, never
because unverifiable accusations flow against it.
------------------------------------------------------------------------------
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .identity import Identity, Envelope, verify, FLPVerifyError

# --- reference constants (shape is normative; numbers are tunable, cf §5.6) - #
W_GOOD = 1.0           # evidence mass of one confirmed-good cooperation
W_DANGLE = 2.0         # soft negative for leaving a cooperation unclosed (§4.4)
W_BAD = 6.0            # confirmed/disputed failure: one defection outweighs
                       #   ~6 cooperations (§3.2 rule 4: super-linear decay)
TRUST_SCALE = 5.0      # net-evidence needed for trust to approach saturation
DECAY = 0.5            # graph-distance decay base (§4.5)
MAX_DEPTH = 2          # testimony horizon (§4.5)
HALF_LIFE_DAYS = 90.0  # time decay of evidence (§4.6)
DANGLING_TIMEOUT_SEC = 7 * 24 * 3600   # grace before unsigned -> dangling


class Verdict(str, Enum):
    FULFILLED = "fulfilled"
    FAILED = "failed"


class CoopState(str, Enum):
    CONFIRMED_GOOD = "confirmed_good"   # both fulfilled -> strong positive
    CONFIRMED_BAD = "confirmed_bad"     # both failed OR disputed -> strong neg
    DANGLING = "dangling"               # one side never signed -> soft negative
    PENDING = "pending"                 # awaiting second signature, within grace


def make_attestation(
    signer: Identity,
    proposal_id: str,
    counterparty: str,
    verdict: Verdict,
    issued_at: Optional[int] = None,
) -> Envelope:
    """Build a signed outcome attestation (§4.3)."""
    body = {
        "type": "outcome_attestation",
        "proposal_id": proposal_id,
        "counterparty": counterparty,
        "verdict": Verdict(verdict).value,
    }
    if issued_at is not None:
        body["issued_at"] = issued_at
    return signer.sign(body)


@dataclass
class Cooperation:
    """A cooperation between two known parties, accumulating their attestations.

    Parties are established when a proposal is accepted (both identities known
    from signed envelopes). Attestations are added as each side closes out.
    """
    proposal_id: str
    party_a: str
    party_b: str
    started_at: float
    _attestations: dict[str, tuple[Verdict, float]] = field(default_factory=dict)

    def add_attestation(self, env: Envelope) -> None:
        """Verify and record one party's signed verdict."""
        body = verify(env, require_fresh=False)  # outcomes may arrive later
        if body.get("type") != "outcome_attestation":
            raise FLPVerifyError("validation_failed", "not an outcome_attestation")
        if body.get("proposal_id") != self.proposal_id:
            raise FLPVerifyError("validation_failed", "proposal_id mismatch")
        signer = env.agent_id
        if signer not in (self.party_a, self.party_b):
            raise FLPVerifyError("validation_failed", "signer is not a party")
        self._attestations[signer] = (
            Verdict(body["verdict"]),
            float(body.get("issued_at", time.time())),
        )

    def resolve(self, now: Optional[float] = None) -> "Resolved":
        now = time.time() if now is None else now
        a = self._attestations.get(self.party_a)
        b = self._attestations.get(self.party_b)

        if a and b:
            va, vb = a[0], b[0]
            age = now - max(a[1], b[1])
            if va == Verdict.FULFILLED and vb == Verdict.FULFILLED:
                return Resolved(CoopState.CONFIRMED_GOOD, self, None, age)
            # mutual failure OR disagreement (disputed) -> bad, edge-local
            return Resolved(CoopState.CONFIRMED_BAD, self, None, age)

        # exactly one (or zero) signature
        signed_by = self.party_a if a else (self.party_b if b else None)
        if now - self.started_at < DANGLING_TIMEOUT_SEC:
            return Resolved(CoopState.PENDING, self, None, 0.0)

        # past grace, still unclosed: the NON-signer is penalized (§4.4)
        if signed_by is None:
            non_signer = None  # neither signed; both dangle (rare; penalize both)
        else:
            non_signer = self.party_b if signed_by == self.party_a else self.party_a
        age = now - self.started_at
        return Resolved(CoopState.DANGLING, self, non_signer, age)


@dataclass
class Resolved:
    state: CoopState
    coop: Cooperation
    penalized: Optional[str]   # for DANGLING: the party who did not sign
    age_sec: float

    @property
    def age_days(self) -> float:
        return self.age_sec / 86400.0

    def parties(self) -> tuple[str, str]:
        return (self.coop.party_a, self.coop.party_b)

    def other(self, me: str) -> Optional[str]:
        if me == self.coop.party_a:
            return self.coop.party_b
        if me == self.coop.party_b:
            return self.coop.party_a
        return None


def _time_weight(age_days: float) -> float:
    return 0.5 ** (max(age_days, 0.0) / HALF_LIFE_DAYS)


def _evidence_to_trust(pos: float, neg: float) -> float:
    """Map weighted evidence mass to trust in [0, 1].

    net <= 0  -> 0.0  (newcomers AND net-negative agents sit at the floor;
                       no benefit of the doubt, per §3.2/§4.5).
    net  > 0  -> 1 - exp(-net / SCALE)  (sub-linear, saturates toward 1).
    """
    net = pos - neg
    if net <= 0:
        return 0.0
    return 1.0 - math.exp(-net / TRUST_SCALE)


class ReputationLedger:
    """An agent's local, relational view of the network.

    Holds the resolved cooperations this agent knows about (its own, plus any
    gathered via gossip/referral). Trust is computed from THIS ledger and is
    therefore the observer's own — there is no global score (§4.1).
    """

    def __init__(self, owner_id: str):
        self.owner_id = owner_id
        self._coops: list[Cooperation] = []

    def record(self, coop: Cooperation) -> None:
        self._coops.append(coop)

    # -- direct trust (depth 0): from the observer's own edges only ---------- #

    def _direct_evidence(self, observer: str, x: str, now: float) -> tuple[float, float]:
        pos = neg = 0.0
        for coop in self._coops:
            r = coop.resolve(now)
            parties = r.parties()
            if observer not in parties or x not in parties or observer == x:
                continue
            w = _time_weight(r.age_days)
            if r.state == CoopState.CONFIRMED_GOOD:
                pos += W_GOOD * w
            elif r.state == CoopState.CONFIRMED_BAD:
                neg += W_BAD * w
            elif r.state == CoopState.DANGLING and r.penalized == x:
                neg += W_DANGLE * w
            # DANGLING where observer is the non-signer says nothing about x
        return pos, neg

    def direct_trust(self, observer: str, x: str, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        pos, neg = self._direct_evidence(observer, x, now)
        return _evidence_to_trust(pos, neg)

    # -- positive testimony others can propagate (only CONFIRMED_GOOD) ------- #

    def _good_partners(self, agent: str, now: float) -> set[str]:
        """Agents with whom `agent` has a CONFIRMED_GOOD (propagatable) edge."""
        out: set[str] = set()
        for coop in self._coops:
            r = coop.resolve(now)
            if r.state == CoopState.CONFIRMED_GOOD:
                p = r.parties()
                if agent in p:
                    out.add(p[0] if p[1] == agent else p[1])
        return out

    def _direct_trust_pairs(self, observer: str, now: float) -> dict[str, float]:
        """observer -> {peer: direct_trust} for peers with positive direct trust."""
        peers: dict[str, float] = {}
        seen: set[str] = set()
        for coop in self._coops:
            for cand in coop.resolve(now).parties():
                if cand == observer or cand in seen:
                    continue
                seen.add(cand)
                t = self.direct_trust(observer, cand, now)
                if t > 0:
                    peers[cand] = t
        return peers

    # -- full relational trust (§4.2, §4.5): direct + propagated testimony --- #

    def trust(self, x: str, observer: Optional[str] = None,
              now: Optional[float] = None) -> float:
        observer = observer or self.owner_id
        now = time.time() if now is None else now

        pos, neg = self._direct_evidence(observer, x, now)  # depth 0, full weight

        # Testimony horizon: BFS over the positive-direct-trust graph to MAX_DEPTH.
        # Each testifier T contributes T's CONFIRMED_GOOD edges with X as positive
        # evidence, gated by path trust * DECAY^path_len. Negatives never propagate.
        frontier: dict[str, float] = {observer: 1.0}  # node -> path trust product
        visited: set[str] = {observer}

        my_peers = self._direct_trust_pairs(observer, now)

        for depth in range(1, MAX_DEPTH + 1):
            nxt: dict[str, float] = {}
            for node, path_trust in frontier.items():
                # who does `node` directly (positively) trust?
                if node == observer:
                    edges = my_peers
                else:
                    edges = self._direct_trust_pairs(node, now)
                for peer, edge_trust in edges.items():
                    if peer in visited or peer == x:
                        continue
                    gate = path_trust * edge_trust * (DECAY ** depth)
                    if gate <= 0:
                        continue
                    # testifier `peer` vouches for X via CONFIRMED_GOOD edges
                    if x in self._good_partners(peer, now):
                        # count peer's good edges with X, time-decayed
                        for coop in self._coops:
                            r = coop.resolve(now)
                            if r.state == CoopState.CONFIRMED_GOOD and \
                               set(r.parties()) == {peer, x}:
                                pos += W_GOOD * _time_weight(r.age_days) * gate
                    nxt[peer] = max(nxt.get(peer, 0.0), path_trust * edge_trust)
                    visited.add(peer)
            frontier = nxt
            if not frontier:
                break

        return _evidence_to_trust(pos, neg)
