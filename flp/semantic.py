"""
Flower of Life Protocol v1.0 — Layer 3 Semantic Matchers (PROTOCOL.md §6.5)

Two ready-to-use semantic functions for the opt-in Layer 3 matching.
Pass one to Matcher(semantic=...).

  sentence_transformer_semantic  — local model via sentence-transformers (recommended)
  ollama_semantic                — local model via Ollama embed API

Both respect the FLP Layer 3 contract:
  - Returns float in (0, 0.50] when similarity is meaningful
  - Returns None when similarity is too low (< threshold)
  - Never exceeds SEMANTIC_MAX_CONFIDENCE (0.50, per §6.7)

Usage:
    from flp import Matcher, Vocabulary
    from flp.semantic import sentence_transformer_semantic

    matcher = Matcher(
        vocab=Vocabulary.core(),
        semantic=sentence_transformer_semantic,
    )

Layer 3 is ADVISORY: the confidence is capped at 0.50 so the cost model
remains cautious about capabilities matched only by semantic similarity.
A high-similarity semantic match at trust=0.0 will still produce a
smaller first cooperation than a Layer 2 synonym match.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Optional

# ── Shared config ────────────────────────────────────────────────────────────

LAYER3_CAP  = 0.50   # FLP §6.7: semantic confidence is advisory, capped here
CACHE_FILE  = Path.home() / ".flp" / "embed_cache.json"


def _cap_to_text(cap: str) -> str:
    """Convert a capability URI to natural language for embedding.

    'flp:cap/finance/crypto-market-signals'
      → 'finance: crypto market signals'

    Natural language produces better embedding quality than raw URIs.
    """
    parts = cap.replace("flp:cap/", "").split("/")
    domain = parts[0] if parts else ""
    leaf   = " ".join(parts[1:]).replace("-", " ") if len(parts) > 1 else ""
    return f"{domain}: {leaf}".strip() if leaf else domain


class _EmbedCache:
    """Persist computed embeddings to disk across sessions."""

    def __init__(self, path: Path = CACHE_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except Exception:
                self._data = {}

    def get(self, key: str) -> Optional[list]:
        return self._data.get(key)

    def set(self, key: str, vec: list) -> None:
        self._data[key] = vec
        self.path.write_text(json.dumps(self._data))


_cache = _EmbedCache()


def _cosine(a: list, b: list) -> float:
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _sim_to_confidence(sim: float, threshold: float) -> Optional[float]:
    """Scale [threshold, 1.0] → (0, LAYER3_CAP], or None below threshold."""
    if sim < threshold:
        return None
    scaled = (sim - threshold) / (1.0 - threshold) * LAYER3_CAP
    return round(min(scaled, LAYER3_CAP), 4)


# ── sentence-transformers (recommended) ──────────────────────────────────────

_ST_MODEL_INSTANCE = None
_ST_MODEL_NAME     = "all-MiniLM-L6-v2"   # 90 MB, fast, good quality
_ST_THRESHOLD      = 0.40                  # calibrated for all-MiniLM-L6-v2


def _get_st_model():
    global _ST_MODEL_INSTANCE
    if _ST_MODEL_INSTANCE is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "pip install sentence-transformers  "
                "(or: pip install sentence-transformers --break-system-packages)"
            )
        _ST_MODEL_INSTANCE = SentenceTransformer(_ST_MODEL_NAME)
    return _ST_MODEL_INSTANCE


def sentence_transformer_semantic(a: str, b: str) -> Optional[float]:
    """Layer 3 matcher using sentence-transformers (all-MiniLM-L6-v2).

    Works fully offline after the first download (~90 MB).
    No Ollama, no API keys required.

    Install: pip install sentence-transformers
    """
    a_text = _cap_to_text(a)
    b_text = _cap_to_text(b)
    model_id = f"st:{_ST_MODEL_NAME}"

    key_a = hashlib.md5(f"{model_id}:{a_text}".encode()).hexdigest()
    key_b = hashlib.md5(f"{model_id}:{b_text}".encode()).hexdigest()

    vec_a = _cache.get(key_a)
    vec_b = _cache.get(key_b)

    try:
        model = _get_st_model()
        if vec_a is None:
            vec_a = model.encode(a_text, normalize_embeddings=True).tolist()
            _cache.set(key_a, vec_a)
        if vec_b is None:
            vec_b = model.encode(b_text, normalize_embeddings=True).tolist()
            _cache.set(key_b, vec_b)
    except Exception:
        return None

    sim = _cosine(vec_a, vec_b)
    return _sim_to_confidence(sim, _ST_THRESHOLD)


# ── Ollama embed API ─────────────────────────────────────────────────────────

_OLLAMA_URL       = "http://localhost:11434/api/embed"
_OLLAMA_MODEL     = "nomic-embed-text"     # ollama pull nomic-embed-text
_OLLAMA_THRESHOLD = 0.72                   # nomic-embed-text operates at higher range


def ollama_semantic(a: str, b: str) -> Optional[float]:
    """Layer 3 matcher using Ollama embed API (nomic-embed-text).

    Requires Ollama running locally with an embedding model installed:
        ollama pull nomic-embed-text

    Falls back silently to None if Ollama is unreachable.
    """
    try:
        import httpx
    except ImportError:
        return None

    a_text   = _cap_to_text(a)
    b_text   = _cap_to_text(b)
    model_id = f"ollama:{_OLLAMA_MODEL}"

    key_a = hashlib.md5(f"{model_id}:{a_text}".encode()).hexdigest()
    key_b = hashlib.md5(f"{model_id}:{b_text}".encode()).hexdigest()

    def _fetch(text: str) -> Optional[list]:
        cached = _cache.get(hashlib.md5(f"{model_id}:{text}".encode()).hexdigest())
        if cached:
            return cached
        try:
            resp = httpx.post(_OLLAMA_URL,
                              json={"model": _OLLAMA_MODEL, "input": text},
                              timeout=15.0)
            resp.raise_for_status()
            body = resp.json()
            vec  = body.get("embeddings", [body.get("embedding")])[0]
            _cache.set(hashlib.md5(f"{model_id}:{text}".encode()).hexdigest(), vec)
            return vec
        except Exception:
            return None

    vec_a = _fetch(a_text)
    vec_b = _fetch(b_text)
    if vec_a is None or vec_b is None:
        return None

    sim = _cosine(vec_a, vec_b)
    return _sim_to_confidence(sim, _OLLAMA_THRESHOLD)
