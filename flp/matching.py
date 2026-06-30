"""
Flower of Life Protocol v1.0 — Matching & Capability Namespacing (PROTOCOL.md §6)

Replaces v0.1's exact-string set-intersection (which silently required two
strangers to pre-agree on identical token spellings). Three degrading layers,
each emitting a match_confidence the §5 cost model consumes via §6.7:

  Layer 1  exact namespaced URI            -> confidence 1.0
  Layer 2  core vocabulary synonym         -> confidence ~0.8
  Layer 3  local semantic matcher (opt-in) -> confidence ~0.5 (advisory)

ADVERSARIAL BY DESIGN (§6.6): a declared surplus is a CLAIM, not a fact. A
match only establishes that cooperation is TOPICALLY POSSIBLE — it never
confers trust. This module therefore does not touch reputation. The surplus
inflator is defeated downstream by the cost model + reputation (small first
exchanges, reputation cost on failure), not by detection here.

"No central authority" forbids a runtime REGISTRY, not a shared REFERENCE: the
core vocabulary is a forkable file (a Schelling point), and Layer 3 runs
LOCALLY inside each agent (no shared oracle). Two agents may legitimately reach
different match conclusions — that mirrors §4's relational reputation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from .cost_model import MatchedItem

# confidence ceilings per layer (shape normative, numbers tunable)
EXACT_CONFIDENCE = 1.0
VOCAB_CONFIDENCE = 0.8
SEMANTIC_MAX_CONFIDENCE = 0.5

_CAP_RE = re.compile(r"^flp:cap/([a-z0-9\-]+)/([a-z0-9\-/]+)$")


# --------------------------------------------------------------------------- #
# Capability URIs (§6.3)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Capability:
    """A validated, normalized capability URI: flp:cap/<domain>/<path>."""
    raw: str
    domain: str
    path: str

    @classmethod
    def parse(cls, s: str) -> "Capability":
        norm = s.strip().lower()
        m = _CAP_RE.match(norm)
        if not m:
            raise ValueError(
                f"malformed capability URI: {s!r} "
                f"(expected flp:cap/<domain>/<path>)"
            )
        return cls(raw=norm, domain=m.group(1), path=m.group(2))

    @staticmethod
    def is_valid(s: str) -> bool:
        try:
            Capability.parse(s)
            return True
        except ValueError:
            return False

    def __str__(self) -> str:
        return self.raw


# --------------------------------------------------------------------------- #
# Forkable core vocabulary (§6.4)
# --------------------------------------------------------------------------- #

class Vocabulary:
    """A forkable synonym map. Convention, not authority (§6.4).

    Built from {canonical_uri: [alias_uri, ...]}. Anyone extends it by editing
    the file or forking — there is no approval gate and no runtime registry.
    """

    def __init__(self, synonyms: Optional[dict[str, list[str]]] = None,
                 version: str = "flp-core/1"):
        self.version = version
        self._to_canonical: dict[str, str] = {}
        for canonical, aliases in (synonyms or {}).items():
            c = Capability.parse(canonical).raw
            self._to_canonical[c] = c
            for a in aliases:
                self._to_canonical[Capability.parse(a).raw] = c

    def canonical(self, cap: str) -> str:
        """Map an alias to its canonical URI; unknown URIs map to themselves."""
        norm = Capability.parse(cap).raw
        return self._to_canonical.get(norm, norm)

    @classmethod
    def core(cls) -> "Vocabulary":
        """Load the bundled core vocabulary from vocabulary/core.json.

        core.json is the Schelling point described in PROTOCOL.md §6.4:
        forkable, no approval gate, no runtime registry. Extend it by editing
        the file or pointing from_file() at your own fork.

        Falls back to a minimal hardcoded set if the file is missing.
        """
        import pathlib
        _here = pathlib.Path(__file__).parent
        _core_path = _here.parent / "vocabulary" / "core.json"
        if _core_path.exists():
            return cls.from_file(str(_core_path))
        # Fallback: minimal hardcoded set (file missing or running from zip)
        return cls({
            "flp:cap/data/market-research": [
                "flp:cap/data/market-intelligence",
                "flp:cap/data/market-analysis",
            ],
            "flp:cap/outreach/b2b": [
                "flp:cap/sales/b2b-outreach",
                "flp:cap/outreach/business-development",
            ],
            "flp:cap/tourism/venue-availability": [
                "flp:cap/tourism/venue-booking-data",
            ],
        })

    @classmethod
    def from_file(cls, path: str) -> "Vocabulary":
        """Load a forkable vocabulary file: {"version": str, "synonyms": {...}}.

        This is the mechanism behind §6.4: the vocabulary is a file anyone can
        fork and extend, not a runtime registry anyone must query.
        """
        import json
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(data.get("synonyms", {}), version=data.get("version", "flp-core/1"))

    def to_dict(self) -> dict:
        """Serialize back to the forkable-file shape."""
        synonyms: dict[str, list[str]] = {}
        for alias, canon in self._to_canonical.items():
            if alias == canon:
                synonyms.setdefault(canon, [])
            else:
                synonyms.setdefault(canon, []).append(alias)
        return {"version": self.version, "synonyms": synonyms}


# --------------------------------------------------------------------------- #
# Matcher (§6.5-6.7)
# --------------------------------------------------------------------------- #

# A local semantic matcher: (need_uri, surplus_uri) -> confidence in [0,1] or None.
SemanticFn = Callable[[str, str], Optional[float]]


@dataclass
class Matcher:
    vocab: Optional[Vocabulary] = None
    semantic: Optional[SemanticFn] = None      # opt-in; local only (§6.5)
    exact_conf: float = EXACT_CONFIDENCE
    vocab_conf: float = VOCAB_CONFIDENCE
    semantic_max: float = SEMANTIC_MAX_CONFIDENCE

    def confidence(self, need: str, surplus: str) -> Optional[float]:
        """Best match confidence between one need and one surplus, or None.

        Tries layers in order of certainty; returns the first that fires.
        Invalid URIs never match (they are simply skipped by callers).
        """
        try:
            n = Capability.parse(need).raw
            s = Capability.parse(surplus).raw
        except ValueError:
            return None

        # Layer 1: exact URI.
        if n == s:
            return self.exact_conf

        # Layer 2: core-vocabulary synonym (same canonical concept).
        if self.vocab is not None and self.vocab.canonical(n) == self.vocab.canonical(s):
            return self.vocab_conf

        # Layer 3: local semantic matcher (advisory, capped).
        if self.semantic is not None:
            c = self.semantic(n, s)
            if c is not None and c > 0:
                return min(c, self.semantic_max)

        return None

    def match(
        self,
        my_needs: Iterable[str],
        their_surplus: Iterable[str],
        *,
        direction: str = "i_need",
        magnitudes: Optional[dict[str, float]] = None,
    ) -> list[MatchedItem]:
        """Find capabilities in (my_needs x their_surplus) that match.

        Returns one MatchedItem per matched need, at its best confidence over
        the counterparty's surplus. `direction` labels the flow; `magnitudes`
        optionally sets per-capability stakes (defaults to 1.0).
        """
        magnitudes = magnitudes or {}
        surplus_list = list(their_surplus)
        items: list[MatchedItem] = []
        for need in my_needs:
            best: Optional[float] = None
            for surplus in surplus_list:
                c = self.confidence(need, surplus)
                if c is not None and (best is None or c > best):
                    best = c
            if best is not None:
                key = Capability.parse(need).raw
                items.append(MatchedItem(
                    capability=key,
                    direction=direction,
                    magnitude=magnitudes.get(key, 1.0),
                    match_confidence=best,
                ))
        return items

    def match_cards(
        self,
        my_card: dict,
        their_card: dict,
        *,
        my_magnitudes: Optional[dict[str, float]] = None,
    ) -> dict[str, list[MatchedItem]]:
        """Two-sided match between two cards.

        Returns:
          {"i_need":  things I need that they offer (-> feed §5 cost model),
           "i_offer": things they need that I offer (-> my reciprocal currency)}

        Per §6.6 this only opens the door; whether to act on `i_need` is decided
        entirely by the §5 cost model weighted by §4 reputation.
        """
        return {
            "i_need": self.match(
                my_card.get("needs", []), their_card.get("surplus", []),
                direction="i_need", magnitudes=my_magnitudes,
            ),
            "i_offer": self.match(
                their_card.get("needs", []), my_card.get("surplus", []),
                direction="i_offer",
            ),
        }
