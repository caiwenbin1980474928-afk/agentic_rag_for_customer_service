"""Embedding model factory used by both indexing and retrieval.

Keeping the factory in one place means swapping providers (e.g. to a local
HuggingFace BGE model) only requires editing this file — the chunker, the
vector store, and the retriever stay untouched.
"""
from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.config import get_settings


def get_embeddings() -> Embeddings:
    """Return the embedding model configured via ``Settings``."""
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.embed_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
