"""Run a staged capability gradient eval for E0/E1/E2/E3.

The showcase eval proves that variants behave differently. This script turns
that difference into capability scores that map to the demo architecture:

- E0: retrieval-only baseline
- E1: router, tools, handoff, and governed retrieval/rerank
- E2: E1 plus evidence grading
- E3: E2 plus reflection

Usage:
    python -m eval.run_agentic_gradient_eval --sample-per-category 2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.graph import clear_graph_cache, get_graph


TESTSET = ROOT / "eval" / "testset_agentic_showcase.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

VARIANTS = ["naive", "e1", "e2", "full"]
VARIANT_LABELS = {
    "naive": "E0 Retrieval",
    "e1": "E1 Routed/Tools",
    "e2": "E2 Graded",
    "full": "E3 Full Agentic",
}

KB_GOVERNANCE_CATEGORIES = {"safety", "sop", "requirements", "table"}
TOOL_CATEGORIES = {
    "tool_order",
    "tool_logistics",
    "tool_after_sales",
    "tool_invoice",
    "tool_complaint",
}


def load_cases(path: Path = TESTSET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stratified_sample(
    cases: list[dict[str, Any]],
    *,
    per_category: int,
    seed: int,
) -> list[dict[str, Any]]:
    if per_category <= 0:
        return cases

    rng = random.Random(seed)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        grouped.setdefault(case.get("category", ""), []).append(case)

    selected: list[dict[str, Any]] = []
    for category in sorted(grouped):
        bucket = list(grouped[category])
        rng.shuffle(bucket)
        selected.extend(bucket[:per_category])
    return sorted(selected, key=lambda c: c["id"])


async def run_one(case: dict[str, Any], variant: str, *, timeout_s: float) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        final = await asyncio.wait_for(
            get_graph(variant).ainvoke({"question": case["question"], "steps": []}),
            timeout=timeout_s,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
    except asyncio.TimeoutError:
        return {
            "variant": variant,
            "error": f"timeout after {timeout_s:.0f}s",
            "latency_ms": (time.perf_counter() - t0) * 1000,
            "steps": [],
            "top_knowledge": [],
            "answer_preview": "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "variant": variant,
            "error": str(exc),
            "latency_ms": (time.perf_counter() - t0) * 1000,
            "steps": [],
            "top_knowledge": [],
            "answer_preview": "",
        }

    steps = final.get("steps") or []
    docs = final.get("docs") or []
    tool_result = final.get("tool_result")
    return {
        "variant": variant,
        "route": final.get("route") or "",
        "end_reason": final.get("end_reason") or "",
        "tool_called": any(s.get("node") == "tool_call" for s in steps),
        "tool_ok": None if tool_result is None else tool_result.get("ok"),
        "steps": [s.get("node") for s in steps],
        "top_knowledge": [
            {
                "doc_type": d.metadata.get("doc_type", ""),
                "title": d.metadata.get("title", ""),
                "chunk_type": d.metadata.get("chunk_type", ""),
                "category": d.metadata.get("category", ""),
            }
            for d in docs[:5]
        ],
        "answer_preview": (final.get("answer") or "").replace("\n", " ")[:220],
        "latency_ms": latency_ms,
    }


def has_step(record: dict[str, Any], node: str) -> bool:
    return node in (record.get("steps") or [])


def action_score(category: str, record: dict[str, Any]) -> float:
    if record.get("error"):
        return 0.0
    route = record.get("route", "")
    if category in TOOL_CATEGORIES:
        return float(route == "tool" and record.get("tool_called") is True and record.get("tool_ok") is True)
    if category == "incomplete_id":
        return float(route == "tool" and record.get("tool_called") is True and record.get("tool_ok") is False)
    if category == "handoff":
        return float(route == "handoff" and has_step(record, "human_handoff"))
    if category in KB_GOVERNANCE_CATEGORIES:
        return float(route == "kb" or has_step(record, "retrieve"))
    return float(not record.get("error"))


def governed_context_score(category: str, record: dict[str, Any]) -> float | None:
    if category not in KB_GOVERNANCE_CATEGORIES:
        return None
    if record.get("error"):
        return 0.0

    top = record.get("top_knowledge") or []
    if not top:
        return 0.0

    doc_types = [d.get("doc_type", "") for d in top]
    chunk_types = [d.get("chunk_type", "") for d in top]
    if category == "safety":
        return float(doc_types[0] == "safety")
    if category == "sop":
        return float("sop" in doc_types[:3])
    if category == "requirements":
        return float("requirements" in chunk_types[:3])
    if category == "table":
        return float("table" in doc_types[:3] or "table" in chunk_types[:3])
    return 0.0


def grade_score(category: str, record: dict[str, Any]) -> float | None:
    if category not in KB_GOVERNANCE_CATEGORIES:
        return None
    if record.get("error"):
        return 0.0
    return float(has_step(record, "grade_docs"))


def reflection_score(record: dict[str, Any]) -> float:
    if record.get("error"):
        return 0.0
    return float(has_step(record, "reflect"))


def score_record(case: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    category = case.get("category", "")
    scores = {
        "action": action_score(category, record),
        "governed_context": governed_context_score(category, record),
        "evidence_grade": grade_score(category, record),
        "reflection": reflection_score(record),
        "no_error": float(not record.get("error")),
    }
    return {**record, "scores": scores}


def avg(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def aggregate(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    by_variant: dict[str, list[dict[str, Any]]] = {variant: [] for variant in VARIANTS}
    for case in records:
        for variant_record in case["variants"]:
            by_variant[variant_record["variant"]].append(variant_record)

    metrics: dict[str, dict[str, float]] = {}
    for variant, variant_records in by_variant.items():
        action = avg([r["scores"]["action"] for r in variant_records])
        context_values = [
            r["scores"]["governed_context"]
            for r in variant_records
            if r["scores"]["governed_context"] is not None
        ]
        grade_values = [
            r["scores"]["evidence_grade"]
            for r in variant_records
            if r["scores"]["evidence_grade"] is not None
        ]
        reflection = avg([r["scores"]["reflection"] for r in variant_records])
        no_error = avg([r["scores"]["no_error"] for r in variant_records])
        latency_ms = avg([r.get("latency_ms", 0.0) for r in variant_records])

        context = avg(context_values)
        grade = avg(grade_values)
        capability_score = 100 * (
            0.25 * action
            + 0.25 * context
            + 0.20 * grade
            + 0.20 * reflection
            + 0.10 * no_error
        )
        metrics[variant] = {
            "action_accuracy": action,
            "governed_context_hit": context,
            "evidence_grade_rate": grade,
            "reflection_rate": reflection,
            "no_error_rate": no_error,
            "avg_latency_ms": latency_ms,
            "capability_score": capability_score,
            "n_cases": float(len(variant_records)),
            "n_context_cases": float(len(context_values)),
            "n_grade_cases": float(len(grade_values)),
        }
    return metrics


async def run_cases(cases: list[dict[str, Any]], *, timeout_s: float) -> dict[str, Any]:
    clear_graph_cache()
    records: list[dict[str, Any]] = []
    for idx, case in enumerate(cases, 1):
        print(f"[{idx:02d}/{len(cases)}] {case['id']} {case['category']} | {case['question']}", flush=True)
        variant_results = []
        for variant in VARIANTS:
            raw = await run_one(case, variant, timeout_s=timeout_s)
            rec = score_record(case, raw)
            variant_results.append(rec)
            scores = rec["scores"]
            print(
                f"  {variant:<5} route={rec.get('route',''):<8} "
                f"steps={'->'.join(rec.get('steps', [])):<50} "
                f"action={scores['action']:.0f} "
                f"context={scores['governed_context'] if scores['governed_context'] is not None else '-'} "
                f"grade={scores['evidence_grade'] if scores['evidence_grade'] is not None else '-'} "
                f"reflect={scores['reflection']:.0f} "
                f"{rec.get('latency_ms', 0):.0f}ms"
                + (f" ERROR={rec.get('error')}" if rec.get("error") else ""),
                flush=True,
            )
        records.append({**case, "variants": variant_results})

    metrics = aggregate(records)
    score_line = [metrics[v]["capability_score"] for v in VARIANTS]
    return {
        "variants": VARIANTS,
        "variant_labels": VARIANT_LABELS,
        "metrics": metrics,
        "is_monotonic_gradient": all(a <= b for a, b in zip(score_line, score_line[1:])),
        "records": records,
    }


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def md_escape(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("|", "｜")


def score_token(record: dict[str, Any]) -> str:
    scores = record["scores"]
    context = "-" if scores["governed_context"] is None else f"C{scores['governed_context']:.0f}"
    grade = "-" if scores["evidence_grade"] is None else f"G{scores['evidence_grade']:.0f}"
    return f"A{scores['action']:.0f}/{context}/{grade}/R{scores['reflection']:.0f}"


def knowledge_preview(record: dict[str, Any], *, limit: int = 3) -> str:
    top = record.get("top_knowledge") or []
    if not top:
        return "-"
    items = []
    for doc in top[:limit]:
        doc_type = doc.get("doc_type") or "?"
        title = doc.get("title") or "?"
        chunk_type = doc.get("chunk_type") or "?"
        items.append(f"`{doc_type}:{md_escape(title)}/{chunk_type}`")
    return "<br>".join(items)


def stage_signal(case: dict[str, Any]) -> str:
    by_variant = {rec["variant"]: rec for rec in case["variants"]}
    e0 = by_variant["naive"]
    e1 = by_variant["e1"]
    e2 = by_variant["e2"]
    e3 = by_variant["full"]
    category = case.get("category", "")

    signals: list[str] = []
    if category in TOOL_CATEGORIES and not e0.get("tool_called") and e1.get("tool_called"):
        signals.append("E1+ switches from static retrieval to real-time tool lookup")
    if category == "incomplete_id" and e1.get("tool_called") and e1.get("tool_ok") is False:
        signals.append("E1+ rejects incomplete business IDs instead of inventing a full ID")
    if category == "handoff" and e1.get("route") == "handoff":
        signals.append("E1+ routes escalation intent directly to human handoff")
    if category in KB_GOVERNANCE_CATEGORIES:
        c0 = e0["scores"]["governed_context"]
        c1 = e1["scores"]["governed_context"]
        if c1 == 1.0 and c0 != 1.0:
            signals.append("E1 frontloads the governed doc_type/chunk_type evidence")
        elif c1 == 0.0:
            signals.append("Governed context is still a retrieval optimization target for this case")
    if e2["scores"]["evidence_grade"] == 1.0 and e1["scores"]["evidence_grade"] != 1.0:
        signals.append("E2 adds evidence grading before generation")
    if e3["scores"]["reflection"] == 1.0 and e2["scores"]["reflection"] != 1.0:
        signals.append("E3 adds post-generation reflection")

    return "; ".join(signals) if signals else "Stages execute without an additional observed capability split"


def category_rollup(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in records:
        grouped.setdefault(case["category"], []).append(case)

    rows: list[dict[str, Any]] = []
    for category in sorted(grouped):
        cases = grouped[category]
        row: dict[str, Any] = {"category": category, "n": len(cases)}
        for variant in VARIANTS:
            variant_records = [
                rec
                for case in cases
                for rec in case["variants"]
                if rec["variant"] == variant
            ]
            context_values = [
                rec["scores"]["governed_context"]
                for rec in variant_records
                if rec["scores"]["governed_context"] is not None
            ]
            grade_values = [
                rec["scores"]["evidence_grade"]
                for rec in variant_records
                if rec["scores"]["evidence_grade"] is not None
            ]
            row[variant] = {
                "action": avg([rec["scores"]["action"] for rec in variant_records]),
                "context": None if not context_values else avg(context_values),
                "grade": None if not grade_values else avg(grade_values),
                "reflection": avg([rec["scores"]["reflection"] for rec in variant_records]),
            }
        rows.append(row)
    return rows


def rollup_cell(scores: dict[str, float | None]) -> str:
    context = "-" if scores["context"] is None else f"C{scores['context']:.1f}"
    grade = "-" if scores["grade"] is None else f"G{scores['grade']:.1f}"
    return f"A{scores['action']:.1f}/{context}/{grade}/R{scores['reflection']:.1f}"


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Agentic RAG Gradient Eval",
        "",
        "This report scores the observed staged capabilities of E0/E1/E2/E3 on the same question set.",
        "",
        "## Gradient Summary",
        "",
        f"- Monotonic gradient: **{payload['is_monotonic_gradient']}**",
        "",
        "| stage | action | governed context | evidence grade | reflection | no error | score | avg latency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in VARIANTS:
        m = payload["metrics"][variant]
        lines.append(
            f"| {VARIANT_LABELS[variant]} | {pct(m['action_accuracy'])} | "
            f"{pct(m['governed_context_hit'])} | {pct(m['evidence_grade_rate'])} | "
            f"{pct(m['reflection_rate'])} | {pct(m['no_error_rate'])} | "
            f"{m['capability_score']:.1f} | {m['avg_latency_ms']:.0f} ms |"
        )

    lines.extend([
        "",
        "## Score Legend",
        "",
        "- `A`: action correctness for the case type, such as tool use, handoff, incomplete-ID refusal, or KB route.",
        "- `C`: governed context hit for safety/SOP/requirements/table cases.",
        "- `G`: evidence grading step for governed KB cases.",
        "- `R`: reflection step.",
        "- `-`: metric is not applicable to this case type.",
        "",
        "## Category Rollup",
        "",
        "| category | n | E0 | E1 | E2 | E3 |",
        "| --- | ---: | --- | --- | --- | --- |",
    ])
    for row in category_rollup(payload["records"]):
        lines.append(
            f"| {row['category']} | {row['n']} | "
            f"{rollup_cell(row['naive'])} | {rollup_cell(row['e1'])} | "
            f"{rollup_cell(row['e2'])} | {rollup_cell(row['full'])} |"
        )

    lines.extend([
        "",
        "## Case Matrix",
        "",
        "| id | category | question | E0 | E1 | E2 | E3 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for case in payload["records"]:
        cells = []
        for rec in case["variants"]:
            cells.append(f"{score_token(rec)} `{'->'.join(rec.get('steps', []))}`")
        question = md_escape(case["question"])
        lines.append(
            f"| {case['id']} | {case['category']} | {question} | "
            f"{cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |"
        )

    lines.extend(["", "## Expanded Case Details", ""])
    for case in payload["records"]:
        lines.append(f"### {case['id']} · {case['category']}")
        lines.append("")
        lines.append(f"**Question:** {md_escape(case['question'])}")
        lines.append("")
        if case.get("difference_focus"):
            lines.append(f"**Expected signal:** {md_escape(case['difference_focus'])}")
            lines.append("")
        lines.append(f"**Observed signal:** {stage_signal(case)}")
        lines.append("")
        lines.append("| stage | route | steps | score | tool | latency | top evidence | answer preview |")
        lines.append("| --- | --- | --- | --- | --- | ---: | --- | --- |")
        for rec in case["variants"]:
            top = knowledge_preview(rec)
            tool = f"{rec.get('tool_called')} / {rec.get('tool_ok')}"
            steps = "`" + "->".join(rec.get("steps", [])) + "`"
            answer = md_escape(rec.get("answer_preview", ""))
            if rec.get("error"):
                answer = f"ERROR: {md_escape(rec['error'])}"
            lines.append(
                f"| {VARIANT_LABELS[rec['variant']]} | {md_escape(rec.get('route'))} | "
                f"{steps} | {score_token(rec)} | {tool} | "
                f"{rec.get('latency_ms', 0):.0f} ms | {top} | {answer} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=0, help="limit cases for a faster smoke run")
    parser.add_argument("--sample-per-category", type=int, default=2, help="stratified sample size per category")
    parser.add_argument("--sample-seed", type=int, default=7)
    parser.add_argument("--testset", type=Path, default=TESTSET)
    parser.add_argument("--timeout-s", type=float, default=70.0, help="per variant/case timeout")
    args = parser.parse_args()

    cases = load_cases(args.testset)
    cases = stratified_sample(cases, per_category=args.sample_per_category, seed=args.sample_seed)
    if args.max_cases:
        cases = cases[: args.max_cases]

    payload = asyncio.run(run_cases(cases, timeout_s=args.timeout_s))
    out_json = RESULTS_DIR / "agentic_gradient.json"
    out_md = RESULTS_DIR / "agentic_gradient.md"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, out_md)

    print(json.dumps({
        "is_monotonic_gradient": payload["is_monotonic_gradient"],
        "scores": {
            VARIANT_LABELS[v]: round(payload["metrics"][v]["capability_score"], 1)
            for v in VARIANTS
        },
    }, ensure_ascii=False, indent=2))
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
