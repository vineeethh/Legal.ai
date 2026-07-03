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

import numpy as np
from FlagEmbedding import BGEM3FlagModel, FlagReranker

from .chunking import Chunk
from .config import get_settings

_embed_model: BGEM3FlagModel | None = None
_reranker: FlagReranker | None = None


def get_embed_model() -> BGEM3FlagModel:
    global _embed_model
    if _embed_model is None:
        _embed_model = BGEM3FlagModel(get_settings().embedding_model, use_fp16=False)
    return _embed_model


def get_reranker() -> FlagReranker:
    global _reranker
    if _reranker is None:
        _reranker = FlagReranker(get_settings().reranker_model, use_fp16=False)
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
