"""
Flower of Life Protocol (FLP) v1.0 — reference implementation.

A protocol for matching and trust between autonomous agents that do not know
each other. Identity is a key (no registry); reputation is relational (no global
score); cooperation is decided by a cost model that bites; matching survives
without a shared vocabulary; discovery and outcomes are signed end to end.

Spec: PROTOCOL.md.  License: MIT.
"""

from .identity import (
    FLP_VERSION, Identity, Envelope, NonceCache, FLPVerifyError, verify,
    encode_did_key, decode_did_key, canonical, new_nonce,
)
from .reputation import (
    ReputationLedger, Cooperation, Resolved, Verdict, CoopState, make_attestation,
)
from .cost_model import (
    CostModel, CapabilityProfile, MatchedItem, ItemDecision, risk,
)
from .matching import Capability, Vocabulary, Matcher
from .net import validate_endpoint
from .agent import FLPAgent
from .server import FLPServer, FLPClient
# Layer 3 semantic matchers — optional (pip install flp[semantic])
try:
    from .semantic import sentence_transformer_semantic, ollama_semantic
    _SEMANTIC_AVAILABLE = True
except ImportError:
    _SEMANTIC_AVAILABLE = False
    def sentence_transformer_semantic(a, b):  # type: ignore
        raise ImportError("pip install flp[semantic]  or  pip install sentence-transformers")
    def ollama_semantic(a, b):  # type: ignore
        raise ImportError("pip install flp[semantic]  or  pip install httpx")

__version__ = FLP_VERSION

__all__ = [
    "__version__", "FLP_VERSION",
    "Identity", "Envelope", "NonceCache", "FLPVerifyError", "verify",
    "encode_did_key", "decode_did_key", "canonical", "new_nonce",
    "ReputationLedger", "Cooperation", "Resolved", "Verdict", "CoopState",
    "make_attestation",
    "CostModel", "CapabilityProfile", "MatchedItem", "ItemDecision", "risk",
    "Capability", "Vocabulary", "Matcher",
    "validate_endpoint", "FLPAgent", "FLPServer", "FLPClient",
    "sentence_transformer_semantic", "ollama_semantic",
]
