"""End-to-end RAG indexing pipeline.

This module is intentionally thin — it only wires the four explicit RAG steps
together. Each step lives in its own module so the data flow is obvious:

    loader.load_docs              → raw Documents
    chunker.split_documents       → text chunks (with section metadata)
    embedder.get_embeddings       → embedding model
    vectorstore.build_vectorstore → persisted Chroma collection
"""
from __future__ import annotations

from app.config import get_settings
from app.ingestion.chunker import split_documents
from app.ingestion.loader import load_docs
from app.ingestion.vectorstore import build_vectorstore, get_vectorstore

__all__ = ["build_index", "get_vectorstore"]


def build_index(rebuild: bool = False) -> int:
    """Run the full load → chunk → embed → persist pipeline.

    Returns the number of chunks written to the vector store.
    """
    settings = get_settings()

    docs = load_docs(settings.docs_dir)
    chunks = split_documents(docs)
    build_vectorstore(chunks, rebuild=rebuild)
    return len(chunks)
