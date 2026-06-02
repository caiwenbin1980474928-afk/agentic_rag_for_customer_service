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
from app.retrieval.reranker import profile_query, rerank
from app.retrieval.retriever import retrieve_with_scores

DEFAULT_FETCH_MULTIPLIER = 8
DEFAULT_MIN_CANDIDATES = 32


def retrieve_and_rerank(
    query: str,
    k: int | None = None,
    *,
    fetch_multiplier: int = DEFAULT_FETCH_MULTIPLIER,
) -> list[Document]:
    """Return top-``k`` documents for ``query`` after reranking."""
    settings = get_settings()
    k = k or settings.top_k
    over_fetch = max(k * fetch_multiplier, DEFAULT_MIN_CANDIDATES, k)

    profile = profile_query(query)
    candidates = retrieve_with_scores(query, k=over_fetch)
    candidates.extend(_supplemental_candidates(query, k=8))
    docs = rerank(candidates, top_k=k, query=query)
    if profile.wants_safety:
        docs = _frontload_doc_type(docs, candidates, doc_type="safety", k=k, max_front=2)
    return docs


def _frontload_doc_type(
    docs: list[Document],
    candidates: list[tuple[Document, float]],
    *,
    doc_type: str,
    k: int,
    max_front: int = 1,
) -> list[Document]:
    """Ensure governance docs are present and first for matching queries."""
    seen: set[tuple[str, str, int]] = set()

    def key(doc: Document) -> tuple[str, str, int]:
        return (
            str(doc.metadata.get("source", "")),
            str(doc.metadata.get("section", "")),
            int(doc.metadata.get("chunk_index", 0) or 0),
        )

    front: list[Document] = []
    for doc in docs:
        if str(doc.metadata.get("doc_type", "")).lower() == doc_type:
            front.append(doc)
            seen.add(key(doc))
        if len(front) >= max_front:
            break

    if len(front) < max_front:
        for doc, _score in sorted(candidates, key=lambda item: item[1]):
            if str(doc.metadata.get("doc_type", "")).lower() != doc_type:
                continue
            doc_key = key(doc)
            if doc_key in seen:
                continue
            front.append(doc)
            seen.add(doc_key)
            if len(front) >= max_front:
                break

    out = list(front)
    seen = {key(doc) for doc in out}
    for doc in docs:
        doc_key = key(doc)
        if doc_key in seen:
            continue
        out.append(doc)
        seen.add(doc_key)
        if len(out) >= k:
            break
    return out[:k]


def _supplemental_candidates(query: str, k: int) -> list[tuple[Document, float]]:
    """Guarantee governance asset types get a chance to rerank.

    Dense retrieval can miss very short assets like tool specs or safety rules.
    We fetch a small filtered candidate set for the doc types implied by the
    query, then let the knowledge-aware reranker decide final ordering.
    """
    profile = profile_query(query)
    doc_types: list[str] = []
    if profile.wants_safety:
        doc_types.append("safety")
    if profile.wants_escalation:
        doc_types.append("safety")
    if profile.wants_tool:
        doc_types.append("tool_spec")
    if profile.wants_sop:
        doc_types.append("sop")
    if profile.wants_script:
        doc_types.append("script")
    if profile.wants_table:
        doc_types.append("table")

    out: list[tuple[Document, float]] = []
    for doc_type in dict.fromkeys(doc_types):
        out.extend(retrieve_with_scores(query, k=k, metadata_filter={"doc_type": doc_type}))
    if profile.category:
        out.extend(retrieve_with_scores(query, k=k, metadata_filter={"category": profile.category}))
    if profile.wants_requirements:
        out.extend(retrieve_with_scores(query, k=k, metadata_filter={"chunk_type": "requirements"}))
        if profile.category:
            out.extend(retrieve_with_scores(
                query,
                k=k,
                metadata_filter={"$and": [
                    {"category": profile.category},
                    {"chunk_type": "requirements"},
                ]},
            ))
    return out
