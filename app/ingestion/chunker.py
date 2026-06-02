"""Split raw documents into business-aware RAG chunks.

The customer-service KB is structured as policy docs with stable sections such
as "适用场景", "标准处理流程", "需要用户提供的信息", and "必须转人工或建工单".
Chunking each heading independently produces small, template-heavy fragments.

This module instead groups related sections into complete service units:

* overview: scenario, key points, common user wording
* procedure: principles and standard handling flow
* requirements: required information and directly answerable cases
* escalation: handoff / ticket rules, scripts, related ticket types

Only oversized units fall back to recursive paragraph splitting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Measured on the structured service KB: raw section groups are often
# 330-430 Chinese chars before the retrieval context header is added. A lower
# merge threshold preserves semantic chunk types while still folding genuinely
# tiny leftovers into their neighbor.
MIN_CHUNK_CHARS = 280
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 100

SEPARATORS = ["\n\n", "\n", "。", "；", "，", " "]

BUSINESS_STAGE = {
    "presales": "售前咨询",
    "order": "售中订单",
    "logistics": "物流配送",
    "aftersales": "售后服务",
}

CHUNK_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("overview", ("适用场景", "主题要点")),
    ("procedure", ("客服处理原则", "标准处理流程")),
    ("requirements", ("需要用户提供的信息", "可直接答复的情况")),
    ("escalation", ("必须转人工或建工单的情况", "示例话术", "相关工单类型")),
]

H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Section:
    title: str
    text: str


@dataclass(frozen=True)
class ChunkBlock:
    chunk_type: str
    sections: tuple[Section, ...]


def split_documents(
    documents: list[Document],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Document]:
    """Return business-aware chunks enriched with retrieval metadata."""
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=SEPARATORS,
    )

    out: list[Document] = []
    for doc in documents:
        title, sections = _parse_markdown_sections(doc)
        blocks = _group_sections(sections)
        for block_index, block in enumerate(blocks, 1):
            text = _render_block(doc, title, block)
            section_names = " / ".join(s.title for s in block.sections)
            base_metadata = _chunk_metadata(
                doc=doc,
                title=title,
                block=block,
                section_names=section_names,
                block_index=block_index,
                char_count=len(text),
            )

            if len(text) <= chunk_size:
                out.append(Document(page_content=text, metadata=base_metadata))
                continue

            for part_index, part in enumerate(char_splitter.split_text(text), 1):
                out.append(
                    Document(
                        page_content=part,
                        metadata={
                            **base_metadata,
                            "chunk_id": f"{base_metadata['chunk_id']}_p{part_index:02d}",
                            "char_count": len(part),
                            "split_part": part_index,
                        },
                    )
                )
    return out


def _parse_markdown_sections(doc: Document) -> tuple[str, list[Section]]:
    text = doc.page_content.strip()
    title_match = H1_RE.search(text)
    title = title_match.group(1).strip() if title_match else Path(doc.metadata.get("source", "document")).stem

    matches = list(H2_RE.finditer(text))
    if not matches:
        body = re.sub(r"^#\s+.+?\s*$", "", text, count=1, flags=re.MULTILINE).strip()
        return title, [Section("正文", body)]

    sections: list[Section] = []
    intro_start = title_match.end() if title_match else 0
    intro = text[intro_start:matches[0].start()].strip()
    if intro:
        sections.append(Section("文档概述", intro))

    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append(Section(match.group(1).strip(), body))
    return title, sections


def _group_sections(sections: list[Section]) -> list[ChunkBlock]:
    remaining = list(sections)
    blocks: list[ChunkBlock] = []

    for chunk_type, wanted_titles in CHUNK_GROUPS:
        picked = _take_sections(remaining, wanted_titles)
        if picked:
            blocks.append(ChunkBlock(chunk_type=chunk_type, sections=tuple(picked)))

    if remaining:
        blocks.append(ChunkBlock(chunk_type="reference", sections=tuple(remaining)))

    return _merge_short_blocks(blocks)


def _take_sections(sections: list[Section], wanted_titles: tuple[str, ...]) -> list[Section]:
    picked: list[Section] = []
    keep: list[Section] = []
    for section in sections:
        if any(section.title == wanted or wanted in section.title for wanted in wanted_titles):
            picked.append(section)
        else:
            keep.append(section)
    sections[:] = keep
    return picked


def _merge_short_blocks(blocks: list[ChunkBlock]) -> list[ChunkBlock]:
    if len(blocks) <= 1:
        return blocks

    merged: list[ChunkBlock] = []
    for block in blocks:
        if merged and _sections_len(block.sections) < MIN_CHUNK_CHARS:
            prev = merged[-1]
            merged[-1] = ChunkBlock(
                chunk_type=f"{prev.chunk_type}+{block.chunk_type}",
                sections=prev.sections + block.sections,
            )
        else:
            merged.append(block)
    return merged


def _sections_len(sections: tuple[Section, ...]) -> int:
    return sum(len(section.text) + len(section.title) for section in sections)


def _render_block(doc: Document, title: str, block: ChunkBlock) -> str:
    path = doc.metadata.get("path", doc.metadata.get("source", ""))
    category = doc.metadata.get("category") or _category_from_path(path)
    stage = doc.metadata.get("business_stage") or BUSINESS_STAGE.get(category, category or "通用")
    doc_type = doc.metadata.get("doc_type", "knowledge")
    section_names = " / ".join(section.title for section in block.sections)
    header = [
        f"文档：{title}",
        f"知识类型：{doc_type}",
        f"业务阶段：{stage}",
        f"当前小节：{section_names}",
        "",
    ]
    body: list[str] = []
    for section in block.sections:
        body.append(f"## {section.title}\n\n{section.text.strip()}")
    return ("\n".join(header) + "\n\n".join(body)).strip()


def _chunk_metadata(
    *,
    doc: Document,
    title: str,
    block: ChunkBlock,
    section_names: str,
    block_index: int,
    char_count: int,
) -> dict:
    path = doc.metadata.get("path", doc.metadata.get("source", ""))
    category = doc.metadata.get("category") or _category_from_path(path)
    doc_id = doc.metadata.get("doc_id") or (Path(path).with_suffix("").as_posix().replace("/", "_") if path else Path(title).stem)
    return {
        **doc.metadata,
        "doc_id": doc_id,
        "title": doc.metadata.get("title", title),
        "category": category,
        "business_stage": doc.metadata.get("business_stage") or BUSINESS_STAGE.get(category, category or "通用"),
        "section": section_names,
        "sections": section_names,
        "chunk_type": block.chunk_type,
        "chunk_index": block_index,
        "chunk_id": f"{doc_id}_c{block_index:02d}",
        "char_count": char_count,
    }


def _category_from_path(path: str) -> str:
    parts = Path(path).parts
    return parts[0] if parts else ""
