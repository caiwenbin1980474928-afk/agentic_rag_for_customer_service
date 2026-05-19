"""CLI: build or rebuild the local Chroma knowledge base.

Usage:
    python -m scripts.ingest               # default: wipe & rebuild (safe, idempotent)
    python -m scripts.ingest --no-rebuild  # append-only (advanced; will duplicate
                                           # existing chunks because Chroma.from_documents
                                           # has no content-level dedup)

Default is rebuild=True because Chroma's ``from_documents`` is append-only and
does NOT dedup by content. Re-running an incremental build would silently
double the KB.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingestion.indexer import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the agentic-rag KB")
    parser.add_argument(
        "--no-rebuild",
        dest="rebuild",
        action="store_false",
        help="append to existing collection instead of wiping it first "
             "(WARNING: will duplicate chunks, only use when you know the KB is empty)",
    )
    parser.set_defaults(rebuild=True)
    args = parser.parse_args()

    mode = "rebuild" if args.rebuild else "append"
    print(f"[ingest] building index ({mode})...")
    n = build_index(rebuild=args.rebuild)
    print(f"[ingest] done. {n} chunks indexed.")


if __name__ == "__main__":
    main()
