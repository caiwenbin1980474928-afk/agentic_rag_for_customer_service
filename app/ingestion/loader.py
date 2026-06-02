"""Load governed knowledge assets from a directory."""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document


CONFLICT_COPY_SUFFIXES = (" 2", " 3", " copy", " 副本")
SUPPORTED_SUFFIXES = {".md", ".txt", ".csv", ".json", ".jsonl", ".yaml", ".yml"}
IGNORED_FILENAMES = {"README.md"}


def load_docs(docs_dir: str | Path) -> list[Document]:
    """Read supported knowledge assets under docs_dir as LangChain Documents.

    Markdown assets may start with a simple YAML-like front matter block. We
    parse scalar ``key: value`` pairs into metadata, then strip the front matter
    from page content so it does not pollute retrieval.
    """
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        raise FileNotFoundError(f"Docs dir not found: {docs_path}")

    documents: list[Document] = []
    for file_path in sorted(docs_path.rglob("*")):
        if file_path.name in IGNORED_FILENAMES:
            continue
        if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if _is_conflict_copy(file_path):
            continue
        text, extra_metadata = _read_asset(file_path)
        rel_path = str(file_path.relative_to(docs_path))
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source": file_path.name,
                    "path": rel_path,
                    "asset_group": rel_path.split("/", 1)[0],
                    "file_type": file_path.suffix.lower().lstrip("."),
                    **extra_metadata,
                },
            )
        )
    return documents


def _is_conflict_copy(file_path: Path) -> bool:
    """Skip local sync conflict copies such as ``xxx 2.md``."""
    stem = file_path.stem.lower()
    return any(stem.endswith(suffix) for suffix in CONFLICT_COPY_SUFFIXES)


def _read_asset(file_path: Path) -> tuple[str, dict[str, str]]:
    raw = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return _strip_front_matter(raw)
    if suffix == ".csv":
        return _wrap_structured_text(file_path, raw, "csv"), {
            "doc_type": "table",
            "title": file_path.stem,
            "visibility": "internal",
        }
    if suffix in {".yaml", ".yml"}:
        metadata = _parse_scalar_lines(raw)
        title = metadata.get("title", file_path.stem)
        return _wrap_structured_text(file_path, raw, "yaml", title=title), metadata
    if suffix == ".json":
        return _wrap_structured_text(file_path, _pretty_json(raw), "json"), {
            "doc_type": "structured_data",
            "title": file_path.stem,
            "visibility": "internal",
        }
    if suffix == ".jsonl":
        return _wrap_structured_text(file_path, raw, "jsonl"), {
            "doc_type": "structured_data",
            "title": file_path.stem,
            "visibility": "internal",
        }
    return raw, {}


def _strip_front_matter(text: str) -> tuple[str, dict[str, str]]:
    if not text.startswith("---\n"):
        return text, {}
    end = text.find("\n---", 4)
    if end == -1:
        return text, {}
    front_matter = text[4:end].strip()
    body_start = text.find("\n", end + 4)
    body = text[body_start + 1:] if body_start != -1 else ""
    return body.lstrip(), _parse_scalar_lines(front_matter)


def _parse_scalar_lines(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            metadata[key] = value
    return metadata


def _wrap_structured_text(file_path: Path, text: str, kind: str, *, title: str | None = None) -> str:
    title = title or file_path.stem
    return f"# {title}\n\n## 结构化资产\n\n```{kind}\n{text.strip()}\n```\n"


def _pretty_json(text: str) -> str:
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except Exception:
        return text
