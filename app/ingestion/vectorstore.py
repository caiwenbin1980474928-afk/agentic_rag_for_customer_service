"""Persistent Chroma vector store shared by the indexer and retriever.

* ``build_vectorstore`` — write-path: embed chunks and persist a fresh (or
  appended) collection on disk.
* ``get_vectorstore`` — read-path: open the existing collection for similarity
  search; this is what the retriever consumes.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import get_settings
from app.ingestion.embedder import get_embeddings


EMBED_BATCH_SIZE = 64


def build_vectorstore(chunks: list[Document], rebuild: bool = False) -> Chroma:
    """Embed ``chunks`` and persist them to the local Chroma directory.

    Some OpenAI-compatible embedding providers, including GLM ``embedding-3``,
    cap batch input at 64 texts. Chroma's convenience ``from_documents`` may
    send a larger batch, so we create the collection first and add documents in
    provider-safe batches.
    """
    settings = get_settings()
    chroma_path = Path(settings.chroma_dir)

    if rebuild and chroma_path.exists():
        shutil.rmtree(chroma_path)

    store = Chroma(
        collection_name=settings.collection_name,
        embedding_function=get_embeddings(),
        persist_directory=str(chroma_path),
    )
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start:start + EMBED_BATCH_SIZE]
        ids = [f"chunk-{start + i:06d}" for i in range(len(batch))]
        store.add_documents(batch, ids=ids)
    return store


def get_vectorstore() -> Chroma:
    """Open the existing Chroma collection for read-only similarity search."""
    settings = get_settings()
    return Chroma(
        collection_name=settings.collection_name,
        embedding_function=get_embeddings(),
        persist_directory=str(settings.chroma_path),
    )
