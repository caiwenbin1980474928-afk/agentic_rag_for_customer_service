"""Retrieval pipeline: similarity search → rerank → top-k.

The agent's ``retrieve_node`` calls this single entry point instead of
talking to Chroma directly. That way swapping in BM25, hybrid search, or a
cross-encoder reranker only touches one file.

Pipeline shape::

    query ──► retrieve_with_scores (over-fetch N = k * fetch_multiplier)
                 │
                 ▼
              rerank        (dedup + source-diversity)
                 │
                 ▼
            top-k Documents → returned to the agent
"""
from __future__ import annotations

from langchain_core.documents import Document

from app.config import get_settings
from app.retrieval.reranker import rerank
from app.retrieval.retriever import retrieve_with_scores

DEFAULT_FETCH_MULTIPLIER = 3


def retrieve_and_rerank(
    query: str,
    k: int | None = None,
    *,
    fetch_multiplier: int = DEFAULT_FETCH_MULTIPLIER,
) -> list[Document]:
    """Return top-``k`` documents for ``query`` after reranking."""
    settings = get_settings()
    k = k or settings.top_k
    over_fetch = max(k * fetch_multiplier, k)

    candidates = retrieve_with_scores(query, k=over_fetch)
    return rerank(candidates, top_k=k)
