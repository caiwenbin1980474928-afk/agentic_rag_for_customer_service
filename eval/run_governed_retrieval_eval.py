"""Evaluate governed retrieval without calling the LLM.

This checks whether the retrieval/rerank layer respects knowledge governance:
doc_type preference, category preference, chunk_type preference, exact title
hits, and hard tool-id detection.

Usage:
    python -m eval.run_governed_retrieval_eval
    python -m eval.run_governed_retrieval_eval --k 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.nodes import _extract_business_id
from app.agent.tools import tool_name_for_id
from app.retrieval.pipeline import retrieve_and_rerank


TESTSET = ROOT / "eval" / "testset_governed.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_cases(path: Path = TESTSET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def any_hit(expected: list[str] | None, actual: list[str]) -> bool | None:
    if not expected:
        return None
    return bool(set(expected) & set(actual))


def title_hit(expected: list[str] | None, actual_titles: list[str], actual_paths: list[str]) -> bool | None:
    if not expected:
        return None
    haystack = actual_titles + actual_paths
    return any(exp in item for exp in expected for item in haystack)


def eval_case(case: dict[str, Any], *, k: int) -> dict[str, Any]:
    docs = retrieve_and_rerank(case["question"], k=k)
    metas = [d.metadata for d in docs]
    doc_types = [m.get("doc_type", "") for m in metas]
    categories = [m.get("category", "") for m in metas]
    chunk_types = [m.get("chunk_type", "") for m in metas]
    titles = [m.get("title", "") for m in metas]
    paths = [m.get("path", "") for m in metas]

    lookup_id = _extract_business_id(case["question"])
    actual_tool = tool_name_for_id(lookup_id) if lookup_id else None
    expected_lookup_id = case.get("expected_lookup_id")
    expected_tool = case.get("expected_tool")

    checks = {
        "doc_type_hit": any_hit(case.get("expected_doc_types"), doc_types),
        "category_hit": any_hit(case.get("expected_categories"), categories),
        "chunk_type_hit": any_hit(case.get("expected_chunk_types"), chunk_types),
        "title_hit": title_hit(case.get("expected_titles"), titles, paths),
        "top_doc_type_hit": (
            None if not case.get("expected_top_doc_type")
            else (doc_types[0] == case["expected_top_doc_type"] if doc_types else False)
        ),
        "tool_id_hit": (
            None if not expected_lookup_id
            else lookup_id == expected_lookup_id
        ),
        "tool_name_hit": (
            None if not expected_tool
            else actual_tool == expected_tool
        ),
    }
    passed_checks = [v for v in checks.values() if v is not None]

    return {
        **case,
        "actual_lookup_id": lookup_id,
        "actual_tool": actual_tool,
        "retrieved": [
            {
                "rank": i + 1,
                "doc_type": m.get("doc_type", ""),
                "category": m.get("category", ""),
                "chunk_type": m.get("chunk_type", ""),
                "title": m.get("title", ""),
                "path": m.get("path", ""),
                "section": m.get("section", ""),
            }
            for i, m in enumerate(metas)
        ],
        "checks": checks,
        "pass": all(passed_checks) if passed_checks else True,
    }


def ratio(records: list[dict[str, Any]], check_name: str) -> float:
    values = [r["checks"][check_name] for r in records if r["checks"].get(check_name) is not None]
    if not values:
        return 0.0
    return sum(1 for v in values if v) / len(values)


def metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(records),
        "pass_rate": sum(1 for r in records if r["pass"]) / len(records) if records else 0.0,
        "doc_type_hit": ratio(records, "doc_type_hit"),
        "category_hit": ratio(records, "category_hit"),
        "chunk_type_hit": ratio(records, "chunk_type_hit"),
        "title_hit": ratio(records, "title_hit"),
        "top_doc_type_hit": ratio(records, "top_doc_type_hit"),
        "tool_id_hit": ratio(records, "tool_id_hit"),
        "tool_name_hit": ratio(records, "tool_name_hit"),
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    m = payload["metrics"]
    lines = [
        "# Governed Retrieval Eval",
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key, value in m.items():
        lines.append(f"| {key} | {value:.3f} |" if isinstance(value, float) else f"| {key} | {value} |")

    failures = [r for r in payload["records"] if not r["pass"]]
    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("No failures.")
    else:
        for r in failures:
            top = r["retrieved"][0] if r["retrieved"] else {}
            failed = [k for k, v in r["checks"].items() if v is False]
            lines.append(f"- `{r['id']}` {r['question']} | failed={', '.join(failed)} | top={top.get('doc_type')} / {top.get('title')}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--testset", type=Path, default=TESTSET)
    args = parser.parse_args()

    cases = load_cases(args.testset)
    records = [eval_case(case, k=args.k) for case in cases]
    payload = {"k": args.k, "metrics": metrics(records), "records": records}

    out_json = RESULTS_DIR / "governed_retrieval.json"
    out_md = RESULTS_DIR / "governed_retrieval.md"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, out_md)

    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
