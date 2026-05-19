"""Load markdown / txt documents from a directory."""
from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document


def load_docs(docs_dir: str | Path) -> list[Document]:
    """Read every .md / .txt under docs_dir as a LangChain Document.

    The metadata.source stores the relative file name so it can be used as a
    citation in the UI.
    """
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        raise FileNotFoundError(f"Docs dir not found: {docs_path}")

    documents: list[Document] = []
    for file_path in sorted(docs_path.rglob("*")):
        if file_path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = file_path.read_text(encoding="utf-8")
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source": file_path.name,
                    "path": str(file_path.relative_to(docs_path)),
                },
            )
        )
    return documents
