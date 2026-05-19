"""Split raw documents into RAG-friendly chunks.

Two-stage strategy:
1. Markdown header split — preserves section context as ``metadata.section`` so
   citations can show references like ``退换货政策.md §2``.
2. Recursive character split — keeps every chunk under ``chunk_size`` characters
   for stable embedding behavior and bounded prompt size.
"""
from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

DEFAULT_CHUNK_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 60

HEADERS_TO_SPLIT_ON = [("#", "h1"), ("##", "h2"), ("###", "h3")]
SEPARATORS = ["\n\n", "\n", "。", "；", "，", " "]


def split_documents(
    documents: list[Document],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Document]:
    """Return chunked documents enriched with ``section`` metadata."""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=SEPARATORS,
    )

    out: list[Document] = []
    for doc in documents:
        header_chunks = header_splitter.split_text(doc.page_content)
        for chunk in header_chunks:
            section = chunk.metadata.get("h2") or chunk.metadata.get("h1") or ""
            for sub in char_splitter.split_text(chunk.page_content):
                out.append(
                    Document(
                        page_content=sub,
                        metadata={**doc.metadata, "section": section},
                    )
                )
    return out
