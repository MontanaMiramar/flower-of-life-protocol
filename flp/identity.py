"""
Flower of Life Protocol v1.0 — Identity (PROTOCOL.md §2)

Implements:
  - Ed25519 keypairs (§2.1)
  - Self-certifying agent_id via did:key (§2.2)
  - JCS-canonicalized signed envelopes (§2.3)
  - Freshness + replay defense: issued_at skew, expires_at, nonce (§2.4)

Design note (on record, mirrors §2.2): agent_id IS the public key,
encoded as did:key. Verification needs no registry and no network call —
the identifier carries its own verification key.
"""

from __future__ import annotations

import base64
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional

import base58
import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption,
)

FLP_VERSION = "1.0"

# Multicodec varint prefix for an ed25519 public key (0xed 0x01).
_ED25519_MULTICODEC_PREFIX = b"\xed\x01"
_DID_KEY_PREFIX = "did:key:"

# Freshness defaults (§2.4)
DEFAULT_CLOCK_SKEW_SEC = 300          # ±5 min
DEFAULT_REPLAY_WINDOW_SEC = 600       # 10 min nonce retention
NONCE_BYTES = 16                      # 128-bit


# --------------------------------------------------------------------------- #
# did:key encode / decode (§2.2)
# --------------------------------------------------------------------------- #

def encode_did_key(public_key: Ed25519PublicKey) -> str:
    """Ed25519 public key -> did:key:z... (multicodec + base58btc multibase)."""
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    prefixed = _ED25519_MULTICODEC_PREFIX + raw
    return _DID_KEY_PREFIX + "z" + base58.b58encode(prefixed).decode("ascii")


def decode_did_key(agent_id: str) -> Ed25519PublicKey:
    """did:key:z... -> Ed25519 public key. Raises ValueError on malformed input."""
    if not agent_id.startswith(_DID_KEY_PREFIX):
        raise ValueError("agent_id is not a did:key")
    mb = agent_id[len(_DID_KEY_PREFIX):]
    if not mb.startswith("z"):
        raise ValueError("unsupported multibase (expected base58btc 'z')")
    try:
        decoded = base58.b58decode(mb[1:])
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"invalid base58 in did:key: {e}") from e
    if not decoded.startswith(_ED25519_MULTICODEC_PREFIX):
        raise ValueError("did:key is not an ed25519 key")
    raw = decoded[len(_ED25519_MULTICODEC_PREFIX):]
    if len(raw) != 32:
        raise ValueError(f"bad ed25519 key length: {len(raw)}")
    return Ed25519PublicKey.from_public_bytes(raw)


# --------------------------------------------------------------------------- #
# Canonicalization (§2.3)
# --------------------------------------------------------------------------- #

def canonical(body: dict[str, Any]) -> bytes:
    """RFC 8785 JCS canonical bytes. Deterministic across implementations."""
    return rfc8785.dumps(body)


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class FLPVerifyError(Exception):
    """Raised when an envelope fails verification (sig/freshness/replay)."""
    def __init__(self, code: str, message: str):
        self.code = code              # maps to §8.6 error codes
        super().__init__(f"{code}: {message}")


# --------------------------------------------------------------------------- #
# Nonce cache for replay defense (§2.4)
# --------------------------------------------------------------------------- #

class NonceCache:
    """In-memory seen-nonce store with time-based eviction.

    Reference implementation. A production agent backs this with shared,
    persistent storage so replay defense survives restarts and spans workers.
    """
    def __init__(self, window_sec: int = DEFAULT_REPLAY_WINDOW_SEC):
        self.window_sec = window_sec
        self._seen: dict[str, float] = {}

    def check_and_add(self, nonce: str, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        self._evict(now)
        if nonce in self._seen:
            return False
        self._seen[nonce] = now
        return True

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_sec
        stale = [n for n, t in self._seen.items() if t < cutoff]
        for n in stale:
            del self._seen[n]


def new_nonce() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(NONCE_BYTES)).decode("ascii").rstrip("=")


# --------------------------------------------------------------------------- #
# Signed envelope (§2.3, §8.1)
# --------------------------------------------------------------------------- #

@dataclass
class Envelope:
    """A verified or to-be-verified FLP wire object."""
    flp_version: str
    body: dict[str, Any]
    agent_id: str
    sig: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "flp_version": self.flp_version,
            "body": self.body,
            "agent_id": self.agent_id,
            "sig": self.sig,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Envelope":
        for k in ("flp_version", "body", "agent_id", "sig"):
            if k not in data:
                raise FLPVerifyError("validation_failed", f"envelope missing '{k}'")
        return cls(
            flp_version=data["flp_version"],
            body=data["body"],
            agent_id=data["agent_id"],
            sig=data["sig"],
        )


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #

class Identity:
    """An FLP agent's cryptographic identity. Holds the private key.

    The public key, encoded as did:key, IS the agent_id (§2.2).
    """

    def __init__(self, private_key: Ed25519PrivateKey):
        self._sk = private_key
        self._pk = private_key.public_key()
        self.agent_id = encode_did_key(self._pk)

    # -- construction ------------------------------------------------------- #

    @classmethod
    def generate(cls) -> "Identity":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_private_bytes(cls, raw: bytes) -> "Identity":
        return cls(Ed25519PrivateKey.from_private_bytes(raw))

    def private_bytes(self) -> bytes:
        """Raw 32-byte seed. Store securely; this IS the identity."""
        return self._sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())

    # -- signing ------------------------------------------------------------ #

    def sign_raw(self, data: bytes) -> str:
        """Sign raw bytes (e.g. a Merkle commitment root). Base64 signature.

        For wire objects use sign(); this exists for commitments where the
        signature must cover exactly one digest and nothing else (manifest
        spec §4: the did signs commitment.root — nothing else).
        """
        return base64.b64encode(self._sk.sign(data)).decode("ascii")

    @staticmethod
    def verify_raw(agent_id: str, data: bytes, sig_b64: str) -> bool:
        """Verify a sign_raw() signature against the key inside a did:key."""
        try:
            pub = decode_did_key(agent_id)
            pub.verify(base64.b64decode(sig_b64), data)
            return True
        except Exception:  # noqa: BLE001 — any malformed input is just "no"
            return False

    def sign(self, body: dict[str, Any]) -> Envelope:
        """Wrap a body in a signed envelope. Adds issued_at/nonce if absent."""
        body = dict(body)
        body.setdefault("issued_at", int(time.time()))
        body.setdefault("nonce", new_nonce())
        sig = self._sk.sign(canonical(body))
        return Envelope(
            flp_version=FLP_VERSION,
            body=body,
            agent_id=self.agent_id,
            sig=base64.b64encode(sig).decode("ascii"),
        )


# --------------------------------------------------------------------------- #
# Verification (§2.3, §2.4) — verification precedes parsing (§8.1)
# --------------------------------------------------------------------------- #

def verify(
    envelope: Envelope | dict[str, Any],
    *,
    nonce_cache: Optional[NonceCache] = None,
    clock_skew_sec: int = DEFAULT_CLOCK_SKEW_SEC,
    require_fresh: bool = True,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Verify signature, then freshness, then replay. Return the trusted body.

    Order matters (§8.1): a bad signature is rejected before its body is
    ever interpreted. Raises FLPVerifyError with a §8.6 code on any failure.
    """
    env = envelope if isinstance(envelope, Envelope) else Envelope.from_dict(envelope)
    now = time.time() if now is None else now

    # 1. Signature against the key embedded in agent_id.
    try:
        pub = decode_did_key(env.agent_id)
    except ValueError as e:
        raise FLPVerifyError("validation_failed", str(e)) from e
    try:
        sig_bytes = base64.b64decode(env.sig)
    except Exception as e:  # noqa: BLE001
        raise FLPVerifyError("validation_failed", f"bad signature encoding: {e}") from e
    try:
        pub.verify(sig_bytes, canonical(env.body))
    except InvalidSignature as e:
        raise FLPVerifyError("invalid_signature", "signature does not verify") from e

    # 2. Freshness (§2.4): issued_at within skew, expires_at not past.
    if require_fresh:
        issued_at = env.body.get("issued_at")
        if not isinstance(issued_at, (int, float)):
            raise FLPVerifyError("validation_failed", "missing/invalid issued_at")
        if issued_at > now + clock_skew_sec:
            raise FLPVerifyError("validation_failed", "issued_at is in the future")
        if issued_at < now - clock_skew_sec and "expires_at" not in env.body:
            raise FLPVerifyError("expired", "message outside clock-skew window")
        exp = env.body.get("expires_at")
        if exp is not None and exp < now:
            raise FLPVerifyError("expired", "object has expired")

    # 3. Replay (§2.4): nonce unseen within the window.
    if nonce_cache is not None:
        nonce = env.body.get("nonce")
        if not isinstance(nonce, str):
            raise FLPVerifyError("validation_failed", "missing/invalid nonce")
        if not nonce_cache.check_and_add(nonce, now=now):
            raise FLPVerifyError("replay_detected", "nonce already seen")

    return env.body
