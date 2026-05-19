"""Rerank the top-N similarity hits down to top-K with source diversity.

Current implementation is intentionally lightweight (pure Python, no extra
dependency) but already does two useful things on top of raw vector scores:

1. **Dedup near-duplicates** — chunks with identical ``source + section`` and
   the same leading content are collapsed; this fights the common failure
   mode where the top-K is dominated by one paragraph repeated.
2. **Source-diversity penalty** — each additional chunk from a source we
   already picked gets a score penalty, so the final top-K covers multiple
   documents instead of stacking the same one.

Extension point: swap ``rerank`` with a cross-encoder (e.g.
``BAAI/bge-reranker-v2-m3``) by replacing the body — the public signature and
the call site in ``pipeline.py`` stay the same.
"""
from __future__ import annotations

from langchain_core.documents import Document

DEFAULT_DIVERSITY_PENALTY = 0.15


def _dedup_key(doc: Document) -> tuple[str, str, str]:
    return (
        doc.metadata.get("source", ""),
        doc.metadata.get("section", ""),
        doc.page_content[:100].strip(),
    )


def rerank(
    docs_with_scores: list[tuple[Document, float]],
    top_k: int,
    *,
    diversity_penalty: float = DEFAULT_DIVERSITY_PENALTY,
) -> list[Document]:
    """Return the top-``top_k`` documents after dedup and source-diversity rerank.

    Args:
        docs_with_scores: ``(Document, distance)`` pairs as returned by
            Chroma's ``similarity_search_with_score`` (lower = more similar).
        top_k: Number of documents to keep.
        diversity_penalty: Additive penalty applied each time a source appears
            again. ``0`` disables diversity entirely.
    """
    if not docs_with_scores:
        return []

    seen_keys: set[tuple[str, str, str]] = set()
    unique: list[tuple[Document, float]] = []
    for doc, score in docs_with_scores:
        key = _dedup_key(doc)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append((doc, score))

    source_count: dict[str, int] = {}
    adjusted: list[tuple[Document, float]] = []
    for doc, score in unique:
        src = doc.metadata.get("source", "")
        penalty = diversity_penalty * source_count.get(src, 0)
        adjusted.append((doc, score + penalty))
        source_count[src] = source_count.get(src, 0) + 1

    adjusted.sort(key=lambda x: x[1])
    return [doc for doc, _ in adjusted[:top_k]]
