"""Thin wrapper over Chroma similarity_search returning LangChain Documents.

The only entry point used in production is ``retrieve_with_scores`` — both the
agentic pipeline (``retrieval/pipeline.py``) and the naive baseline node
(``agent/nodes.py:retrieve_node_plain``) go through it. Keeping a single
read-path here means hot-swapping Chroma → Qdrant / Milvus only touches one
file.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.documents import Document

from app.config import get_settings
from app.ingestion.vectorstore import get_vectorstore


@lru_cache(maxsize=1)
def _store():
    return get_vectorstore()


def retrieve_with_scores(query: str, k: int | None = None) -> list[tuple[Document, float]]:
    """Return ``(Document, distance)`` pairs ordered by ascending distance."""
    settings = get_settings()
    k = k or settings.top_k
    return _store().similarity_search_with_score(query, k=k)
