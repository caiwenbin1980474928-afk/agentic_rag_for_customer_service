"""Aggregate the 4 ablation result files into a single comparison report.

Outputs:
    eval/results/comparison.md   — markdown table for the report
    eval/results/comparison.csv  — same data in CSV
    eval/results/case_study.md   — cases where naive is wrong but full is right
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "eval" / "results"

VARIANTS = ["naive", "e1", "e2", "full"]
LABEL = {
    "naive": "E0 Naive RAG",
    "e1": "E1 +路由+工具",
    "e2": "E2 +查询改写",
    "full": "E3 Full Agentic",
}


def _load(variant: str) -> dict | None:
    path = RESULTS_DIR / f"{variant}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt(x: Any) -> str:
    if isinstance(x, float):
        return f"{x:.3f}"
    return str(x)


def build_table() -> tuple[list[str], list[list[str]]]:
    headers = [
        "实验组", "n",
        "路由准确率", "工具F1",
        "Hit@3", "Hit@5", "MRR",
        "Faithfulness", "AnswerRelev.", "ContextPrec.",
        "延迟p50(ms)", "延迟p95(ms)",
    ]
    rows: list[list[str]] = []

    for v in VARIANTS:
        data = _load(v)
        if not data:
            rows.append([LABEL[v]] + ["-"] * (len(headers) - 1))
            continue
        m = data["metrics"]
        ragas = m.get("ragas", {}) or {}
        rows.append([
            LABEL[v],
            str(m.get("n", 0)),
            _fmt(m.get("route_accuracy", 0)),
            _fmt(m.get("tool", {}).get("f1", 0)),
            _fmt(m.get("hit@3", 0)),
            _fmt(m.get("hit@5", 0)),
            _fmt(m.get("mrr", 0)),
            _fmt(ragas.get("faithfulness", 0)),
            _fmt(ragas.get("answer_relevancy", 0)),
            _fmt(ragas.get("context_precision", 0)),
            _fmt(m.get("latency_ms", {}).get("p50", 0)),
            _fmt(m.get("latency_ms", {}).get("p95", 0)),
        ])
    return headers, rows


def write_markdown(headers: list[str], rows: list[list[str]]) -> Path:
    lines = ["# 4 组消融对比", "",
             "| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("> 越大越好：路由准确率、工具 F1、Hit@k、MRR、RAGAS 三项；越小越好：延迟。")
    out = RESULTS_DIR / "comparison.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def write_csv(headers: list[str], rows: list[list[str]]) -> Path:
    out = RESULTS_DIR / "comparison.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    return out


def write_case_study() -> Path | None:
    """Pick cases where naive failed but full succeeded for the report."""
    naive = _load("naive")
    full = _load("full")
    if not naive or not full:
        return None

    naive_by_id = {r["id"]: r for r in naive["records"]}
    full_by_id = {r["id"]: r for r in full["records"]}

    interesting: list[dict] = []
    for cid, fr in full_by_id.items():
        nr = naive_by_id.get(cid)
        if not nr:
            continue
        # heuristic "naive wrong, full right": naive missed expected sources OR
        # naive routed wrong, while full hit expected source and routed right.
        naive_ok = (
            (not fr.get("expected_sources") or
             bool(set(nr["retrieved_sources"][:3]) & set(fr.get("expected_sources", []))))
            and (nr.get("actual_route") == fr.get("expected_route"))
        )
        full_ok = (
            (not fr.get("expected_sources") or
             bool(set(fr["retrieved_sources"][:3]) & set(fr.get("expected_sources", []))))
            and (fr.get("actual_route") == fr.get("expected_route"))
        )
        if (not naive_ok) and full_ok:
            interesting.append({
                "id": cid,
                "question": fr["question"],
                "ground_truth": fr.get("ground_truth", ""),
                "naive_route": nr.get("actual_route"),
                "naive_sources": nr.get("retrieved_sources", [])[:3],
                "naive_answer": nr.get("actual_answer", "")[:200],
                "full_route": fr.get("actual_route"),
                "full_sources": fr.get("retrieved_sources", [])[:3],
                "full_answer": fr.get("actual_answer", "")[:200],
                "expected_sources": fr.get("expected_sources", []),
            })

    out = RESULTS_DIR / "case_study.md"
    lines = ["# 关键案例分析（Naive 错 / Full 对）", ""]
    if not interesting:
        lines.append("（本次运行未发现典型差异案例。）")
    for c in interesting[:5]:
        lines += [
            f"## Case {c['id']}: {c['question']}",
            f"- 参考答案：{c['ground_truth']}",
            f"- E0 Naive RAG：route={c['naive_route']}, 检索={c['naive_sources']}",
            f"  - 回答片段：{c['naive_answer']}",
            f"- E3 Full Agentic：route={c['full_route']}, 检索={c['full_sources']}",
            f"  - 回答片段：{c['full_answer']}",
            "",
        ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    if not RESULTS_DIR.exists():
        print(f"[compare] no results directory: {RESULTS_DIR}")
        sys.exit(1)

    headers, rows = build_table()
    md_path = write_markdown(headers, rows)
    csv_path = write_csv(headers, rows)
    cs_path = write_case_study()
    print(f"[compare] wrote {md_path}")
    print(f"[compare] wrote {csv_path}")
    if cs_path:
        print(f"[compare] wrote {cs_path}")


if __name__ == "__main__":
    main()
