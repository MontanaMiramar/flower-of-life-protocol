"""
FLP Capability Manifest (draft v0.2) — tiered, verifiable capability disclosure.

Spec: docs/CAPABILITY_MANIFEST_spec_v0.2.md (proposed for v1.1).

Implements:
  - Merkle-SHA256 commitment: every field of every tier is a salted leaf;
    the announcer signs ONLY the root (spec §4).
  - `reveal(tier)` -> revealed fields + inclusion proofs.
  - `verify(revealed_fields, proofs, root, signature, did)` -> bool.
  - Requester challenge: proof-of-key before any tier above the open one
    (spec §3), reusing the identity envelope primitives.
  - Tier selection is announcer policy — a callable, never protocol
    constants (spec §1.2).
  - Band/committed-cost mismatch detection — the provable lie (spec §5).

Design note (on record, mirrors spec §4): signing the plaintext manifest
would break verification for anyone served only the open tier. Committing
per salted field and signing the root lets one signature serve every trust
level; hidden leaves stay hidden, revealed leaves stay attributable.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .identity import Identity, decode_did_key, canonical, new_nonce, verify as verify_envelope, FLPVerifyError

# Example tier names from the spec. These are ANNOUNCER POLICY, not protocol
# constants: any tier vocabulary works as long as the announcer's policy and
# tier_order agree. The first tier in the order is the open tier, served to
# any authenticated stranger.
EXAMPLE_TIER_ORDER = ("public", "known", "trusted")

MANIFEST_VERSION = "0.2"
SALT_BYTES = 16

_LEAF_DOMAIN = b"flp-manifest-leaf-v0.2\x00"
_NODE_DOMAIN = b"flp-manifest-node-v0.2\x00"
_ROOT_SIG_CONTEXT = b"flp-manifest-root-v1"


def _root_sig_payload(root: bytes) -> bytes:
    """What the announcer's key actually signs: H(context || root).

    Never the bare root: the same Ed25519 key also signs envelopes
    (identity §2.3), and the context tag makes the two signature domains
    mutually unusable — a manifest-root signature can never be replayed
    as an envelope signature or vice versa.
    """
    return hashlib.sha256(_ROOT_SIG_CONTEXT + root).digest()


# --------------------------------------------------------------------------- #
# Merkle-SHA256 commitment (spec §4)
# --------------------------------------------------------------------------- #

def _leaf_hash(path: str, value: Any, salt: bytes) -> bytes:
    """leaf = H(path || value || salt), domain-separated, JCS-canonical value."""
    return hashlib.sha256(
        _LEAF_DOMAIN + path.encode("utf-8") + b"\x00" + canonical(value) + b"\x00" + salt
    ).digest()


def _node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(_NODE_DOMAIN + left + right).digest()


def _build_levels(leaves: list[bytes]) -> list[list[bytes]]:
    """All levels of the tree, leaves first. Odd nodes are promoted unpaired."""
    if not leaves:
        raise ValueError("cannot commit to an empty manifest")
    levels = [leaves]
    while len(levels[-1]) > 1:
        cur = levels[-1]
        nxt = [
            _node_hash(cur[i], cur[i + 1]) if i + 1 < len(cur) else cur[i]
            for i in range(0, len(cur), 2)
        ]
        levels.append(nxt)
    return levels


def _inclusion_proof(levels: list[list[bytes]], index: int) -> list[list[str]]:
    """Sibling path for one leaf: [["L"|"R", sibling_hex], ...] bottom-up."""
    proof: list[list[str]] = []
    for level in levels[:-1]:
        sibling = index ^ 1
        if sibling < len(level):
            side = "L" if sibling < index else "R"
            proof.append([side, level[sibling].hex()])
        index //= 2
    return proof


def _root_from_proof(leaf: bytes, proof: list[list[str]]) -> bytes:
    h = leaf
    for side, sibling_hex in proof:
        sib = bytes.fromhex(sibling_hex)
        h = _node_hash(sib, h) if side == "L" else _node_hash(h, sib)
    return h


# --------------------------------------------------------------------------- #
# Field flattening
# --------------------------------------------------------------------------- #

def _flatten(agent: dict[str, Any], capabilities: list[dict[str, Any]]) -> dict[str, Any]:
    """Manifest content -> {path: value}. Every field of every tier is one leaf.

    Paths: agent.<field> · capabilities.<i>.id · capabilities.<i>.namespace ·
    capabilities.<i>.disclosure.<tier>.<field>. A tier field's value (however
    nested) is a single leaf: tiers unseal field-by-field, not atom-by-atom.
    """
    fields: dict[str, Any] = {}
    for k, v in agent.items():
        fields[f"agent.{k}"] = v
    for i, cap in enumerate(capabilities):
        for k in ("id", "namespace"):
            if k in cap:
                fields[f"capabilities.{i}.{k}"] = cap[k]
        for tier, tier_fields in cap.get("disclosure", {}).items():
            for k, v in tier_fields.items():
                fields[f"capabilities.{i}.disclosure.{tier}.{k}"] = v
    return fields


def _path_tier(path: str) -> Optional[str]:
    """Tier a leaf belongs to, or None for baseline (agent / id / namespace)."""
    parts = path.split(".")
    if len(parts) >= 5 and parts[0] == "capabilities" and parts[2] == "disclosure":
        return parts[3]
    return None


# --------------------------------------------------------------------------- #
# The manifest (announcer side)
# --------------------------------------------------------------------------- #

@dataclass
class CapabilityManifest:
    """The announcer's private manifest: all fields, all salts, root signature.

    Only `reveal()` output ever goes on the wire; this object never does.
    """
    identity: Identity
    fields: dict[str, Any]
    salts: dict[str, bytes]
    root: bytes
    signature: str                       # base64, over H(context || root) — nothing else
    tier_order: tuple[str, ...]
    _levels: list[list[bytes]] = field(repr=False, default_factory=list)
    _index: dict[str, int] = field(repr=False, default_factory=dict)

    @classmethod
    def build(
        cls,
        identity: Identity,
        capabilities: list[dict[str, Any]],
        *,
        issued_at: str,
        expires_at: str,
        tier_order: tuple[str, ...] = EXAMPLE_TIER_ORDER,
    ) -> "CapabilityManifest":
        agent = {"did": identity.agent_id, "issued_at": issued_at, "expires_at": expires_at}
        fields = _flatten(agent, capabilities)
        paths = sorted(fields)                       # deterministic leaf order
        salts = {p: secrets.token_bytes(SALT_BYTES) for p in paths}
        leaves = [_leaf_hash(p, fields[p], salts[p]) for p in paths]
        levels = _build_levels(leaves)
        root = levels[-1][0]
        return cls(
            identity=identity,
            fields=fields,
            salts=salts,
            root=root,
            signature=identity.sign_raw(_root_sig_payload(root)),
            tier_order=tuple(tier_order),
            _levels=levels,
            _index={p: i for i, p in enumerate(paths)},
        )

    def reveal(self, tier: Optional[str] = None) -> dict[str, Any]:
        """Fields + inclusion proofs for `tier` and every tier below it.

        `tier=None` (or the first tier in tier_order) is the open tier:
        baseline fields (agent.*, capability ids/namespaces) plus the first
        tier's disclosure. Disclosure is cumulative — a counterparty trusted
        with `known` also needs `public` to match on.
        """
        tier = tier or self.tier_order[0]
        if tier not in self.tier_order:
            raise ValueError(f"unknown tier {tier!r} (order: {self.tier_order})")
        allowed = set(self.tier_order[: self.tier_order.index(tier) + 1])

        revealed: dict[str, Any] = {}
        proofs: dict[str, dict[str, Any]] = {}
        for path, value in self.fields.items():
            leaf_tier = _path_tier(path)
            if leaf_tier is not None and leaf_tier not in allowed:
                continue
            revealed[path] = value
            proofs[path] = {
                "salt": self.salts[path].hex(),
                "siblings": _inclusion_proof(self._levels, self._index[path]),
            }
        return {
            "manifest_version": MANIFEST_VERSION,
            "revealed": revealed,
            "proofs": proofs,
            "commitment": {"alg": "merkle-sha256", "root": self.root.hex()},
            "signature": {"alg": "Ed25519", "value": self.signature},
        }


# --------------------------------------------------------------------------- #
# Verification (receiver side)
# --------------------------------------------------------------------------- #

def verify_manifest(
    revealed_fields: dict[str, Any],
    proofs: dict[str, dict[str, Any]],
    root: str,
    signature: str,
    did: str,
) -> bool:
    """True iff the signature covers `root` under `did`'s key AND every
    revealed field recomputes to that root through its inclusion proof.

    Learns nothing about unrevealed leaves (spec §4.4). Verification precedes
    interpretation, as everywhere in FLP (§8.1).
    """
    try:
        root_bytes = bytes.fromhex(root)
        if not Identity.verify_raw(did, _root_sig_payload(root_bytes), signature):
            return False
        for path, value in revealed_fields.items():
            proof = proofs[path]
            leaf = _leaf_hash(path, value, bytes.fromhex(proof["salt"]))
            if _root_from_proof(leaf, proof["siblings"]) != root_bytes:
                return False
    except (KeyError, ValueError, TypeError):
        return False
    # The did itself must be a committed, revealed leaf that matches the signer.
    return revealed_fields.get("agent.did") == did


def verify_reveal(bundle: dict[str, Any], did: str) -> bool:
    """Convenience: verify a `reveal()` bundle as shipped."""
    return verify_manifest(
        bundle["revealed"],
        bundle["proofs"],
        bundle["commitment"]["root"],
        bundle["signature"]["value"],
        did,
    )


# --------------------------------------------------------------------------- #
# Requester challenge + announcer-policy tier selection (spec §3, §1.2)
# --------------------------------------------------------------------------- #

# An announcer's disclosure policy: requester did -> tier name to serve.
# A policy typically wraps the announcer's ReputationLedger; the protocol
# never defines the thresholds.
TierPolicy = Callable[[str], str]


class ManifestDiscloser:
    """Announcer-side disclosure endpoint logic (transport-agnostic).

    Serves the open tier to anyone; serves higher tiers only after
    proof-of-key (challenge nonce signed by the requester's claimed did),
    and then only as far as the announcer's own policy permits.
    """

    def __init__(self, manifest: CapabilityManifest, tier_policy: TierPolicy):
        self.manifest = manifest
        self.tier_policy = tier_policy
        self._challenges: dict[str, str] = {}      # requester_did -> nonce

    def challenge(self, requester_did: str) -> str:
        nonce = new_nonce()
        self._challenges[requester_did] = nonce
        return nonce

    def request(
        self,
        requester_did: str,
        tier: Optional[str] = None,
        challenge_response: Optional[dict[str, Any] | Any] = None,
    ) -> dict[str, Any]:
        """Serve a reveal. Without a valid proof-of-key: open tier only."""
        open_tier = self.manifest.tier_order[0]
        if tier is None or tier == open_tier:
            return self.manifest.reveal(open_tier)
        if not self._proof_of_key_ok(requester_did, challenge_response):
            return self.manifest.reveal(open_tier)          # spec §3: at most open
        granted = self.tier_policy(requester_did)
        order = self.manifest.tier_order
        served = tier if order.index(tier) <= order.index(granted) else granted
        return self.manifest.reveal(served)

    def _proof_of_key_ok(self, requester_did: str, response: Any) -> bool:
        expected = self._challenges.pop(requester_did, None)
        if expected is None or response is None:
            return False
        try:
            body = verify_envelope(response, require_fresh=False)
        except FLPVerifyError:
            return False
        env_agent = response["agent_id"] if isinstance(response, dict) else response.agent_id
        return (
            body.get("type") == "manifest_tier_challenge"
            and body.get("challenge") == expected
            and env_agent == requester_did
        )


def answer_challenge(identity: Identity, nonce: str):
    """Requester side: sign the announcer's nonce with the claimed did's key."""
    return identity.sign({"type": "manifest_tier_challenge", "challenge": nonce})


# --------------------------------------------------------------------------- #
# The provable lie: band vs. committed cost (spec §5)
# --------------------------------------------------------------------------- #

# Reference band bounds (per-call USD). Like every constant in FLP, the
# SHAPE is normative (band must contain the committed cost), the numbers
# are the verifier's business.
REFERENCE_BAND_BOUNDS: dict[str, tuple[float, float]] = {
    "low": (0.0, 0.01),
    "mid": (0.01, 1.0),
    "high": (1.0, float("inf")),
}


def band_mismatch(
    cost_band: str,
    committed_cost: dict[str, Any] | float,
    bounds: Optional[dict[str, tuple[float, float]]] = None,
) -> bool:
    """True iff the committed exact cost falls outside the announced band.

    Both inputs come from *verified* leaves of the same root, so a mismatch
    is attributable and non-repudiable. Implementations MUST treat it as a
    failed outcome for reputation purposes (spec §5).
    """
    bounds = REFERENCE_BAND_BOUNDS if bounds is None else bounds
    if cost_band not in bounds:
        return True
    value = committed_cost["value"] if isinstance(committed_cost, dict) else committed_cost
    lo, hi = bounds[cost_band]
    return not (lo <= float(value) < hi)
