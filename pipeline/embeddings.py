"""Embedding + rerank models (BAAI/bge-m3, bge-reranker-v2-m3), run locally.

Two distinct uses:
  - Statute KB (persistent): embeddings are written to Qdrant by statute_kb/ingest.py.
  - Judgment self-retrieval (ephemeral, per run): the retrieval-fallback path in
    docs/architecture/data_flow.md re-embeds a single document's own chunks so an
    agent whose structure-routed input is thin can pull additional chunks by
    similarity. This is small (one document, a few hundred chunks) and lives
    only for the duration of a run, so it's an in-memory index rather than a
    Qdrant collection — no persistence, no lifecycle to manage.
"""

from __future__ import annotations

import threading

import numpy as np
from FlagEmbedding import BGEM3FlagModel
from sentence_transformers import CrossEncoder

from .chunking import Chunk
from .config import get_settings

_embed_model: BGEM3FlagModel | None = None
_reranker: "_CrossEncoderReranker | None" = None
# These models are large and lazily built. The 6 extraction agents fan out
# concurrently (LangGraph Pregel), so without a lock two threads can race into
# building the same model at once — wasteful re-load and a memory spike.
_embed_lock = threading.Lock()
_reranker_lock = threading.Lock()


class _CrossEncoderReranker:
    """bge-reranker-v2-m3 via sentence-transformers' CrossEncoder.

    Replaces FlagEmbedding.FlagReranker, whose compute_score() calls the
    tokenizer's prepare_for_model() — a method transformers 5.x removed. (The
    BGE-M3 *embedder* uses a different code path that is unaffected, so it
    stays on FlagEmbedding.) CrossEncoder loads the same model and is
    transformers-5 compatible. It keeps the exact compute_score(pairs,
    normalize=True) contract the call sites already use: one logit per pair,
    sigmoid-mapped to [0,1] when normalize=True, so the existing 0.55
    similarity thresholds (router fallback, statute verification) are unchanged.
    """

    def __init__(self, model_name: str):
        self._ce = CrossEncoder(model_name)

    def compute_score(self, pairs: list[list[str]], normalize: bool = True) -> list[float]:
        if not pairs:
            return []
        scores = np.asarray(self._ce.predict(pairs), dtype=float)
        if normalize:
            scores = 1.0 / (1.0 + np.exp(-scores))
        return scores.tolist()


def get_embed_model() -> BGEM3FlagModel:
    global _embed_model
    if _embed_model is None:  # fast path: no lock once built
        with _embed_lock:
            if _embed_model is None:  # re-check under the lock
                _embed_model = BGEM3FlagModel(get_settings().embedding_model, use_fp16=False)
    return _embed_model


def get_reranker() -> "_CrossEncoderReranker":
    global _reranker
    if _reranker is None:
        with _reranker_lock:
            if _reranker is None:
                _reranker = _CrossEncoderReranker(get_settings().reranker_model)
    return _reranker


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 1024), dtype=np.float32)
    out = get_embed_model().encode(texts, return_dense=True)
    return np.asarray(out["dense_vecs"], dtype=np.float32)


class JudgmentChunkIndex:
    """In-memory cosine-similarity index over one document's own chunks.

    Built once per run after chunking; used by the retrieval-fallback path
    when structure-first routing finds too few chunks for an agent.
    """

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._vectors = embed_texts([c.text for c in chunks])
        norms = np.linalg.norm(self._vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._unit = self._vectors / norms

    def search(self, query: str, top_k: int = 10) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        q = embed_texts([query])[0]
        q_norm = np.linalg.norm(q) or 1.0
        q_unit = q / q_norm
        scores = self._unit @ q_unit
        top_idx = np.argsort(-scores)[:top_k]
        return [(self.chunks[i], float(scores[i])) for i in top_idx]

    def rerank(self, query: str, candidates: list[Chunk], top_k: int = 5) -> list[tuple[Chunk, float]]:
        if not candidates:
            return []
        pairs = [[query, c.text] for c in candidates]
        scores = get_reranker().compute_score(pairs, normalize=True)
        if isinstance(scores, float):
            scores = [scores]
        ranked = sorted(zip(candidates, scores), key=lambda x: -x[1])
        return ranked[:top_k]
