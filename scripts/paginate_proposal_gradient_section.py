from __future__ import annotations

from pathlib import Path

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
DOCX_PATH = ROOT / "Agentic_RAG_Project_Proposal_EN.docx"


def main() -> None:
    doc = Document(DOCX_PATH)
    for paragraph in doc.paragraphs:
        if paragraph.text.strip() == "Latest staged ablation results":
            paragraph.paragraph_format.page_break_before = True
            paragraph.paragraph_format.keep_with_next = True
        if paragraph.text.strip() == "Representative case signals":
            paragraph.paragraph_format.keep_with_next = True
    doc.save(DOCX_PATH)
    print(f"Paginated {DOCX_PATH}")


if __name__ == "__main__":
    main()
