"""Run an agentic RAG showcase comparison across E0/E1/E2/E3.

This is intentionally different from the normal benchmark. It is built for
demo/defense: each case is chosen to expose a capability difference such as
tool use, handoff, safety, SOP retrieval, grading, rewriting, or reflection.

Usage:
    python -m eval.run_agentic_showcase_eval
    python -m eval.run_agentic_showcase_eval --max-cases 8
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
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
            "answer_preview": "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "variant": variant,
            "error": str(exc),
            "latency_ms": (time.perf_counter() - t0) * 1000,
            "steps": [],
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
            f"{d.metadata.get('doc_type','')}:{d.metadata.get('title','')}/{d.metadata.get('chunk_type','')}"
            for d in docs[:3]
        ],
        "answer_preview": (final.get("answer") or "").replace("\n", " ")[:180],
        "latency_ms": latency_ms,
    }


def signature(record: dict[str, Any]) -> str:
    return "|".join([
        str(record.get("route", "")),
        ",".join(record.get("steps", [])),
        f"tool={record.get('tool_called')}",
        f"end={record.get('end_reason', '')}",
    ])


async def run_cases(cases: list[dict[str, Any]], *, timeout_s: float) -> dict[str, Any]:
    clear_graph_cache()
    records: list[dict[str, Any]] = []
    for idx, case in enumerate(cases, 1):
        print(f"[{idx:02d}/{len(cases)}] {case['id']} {case['question']}", flush=True)
        variant_results = []
        for variant in VARIANTS:
            rec = await run_one(case, variant, timeout_s=timeout_s)
            variant_results.append(rec)
            print(
                f"  {variant:<5} route={rec.get('route',''):<8} "
                f"steps={'->'.join(rec.get('steps', [])):<45} "
                f"tool={rec.get('tool_called')} {rec.get('latency_ms', 0):.0f}ms"
                + (f" ERROR={rec.get('error')}" if rec.get("error") else ""),
                flush=True,
            )
        sigs = {signature(r) for r in variant_results}
        records.append({
            **case,
            "variants": variant_results,
            "distinct_signatures": len(sigs),
            "distinguishes_variants": len(sigs) > 1,
        })
    metrics = {
        "n_cases": len(records),
        "n_distinguishing_cases": sum(1 for r in records if r["distinguishes_variants"]),
        "n_errors": sum(1 for r in records for v in r["variants"] if v.get("error")),
        "distinguishing_rate": (
            sum(1 for r in records if r["distinguishes_variants"]) / len(records)
            if records else 0.0
        ),
        "error_rate": (
            sum(1 for r in records for v in r["variants"] if v.get("error")) / (len(records) * len(VARIANTS))
            if records else 0.0
        ),
        "avg_distinct_signatures": (
            sum(r["distinct_signatures"] for r in records) / len(records)
            if records else 0.0
        ),
    }
    return {"variants": VARIANTS, "metrics": metrics, "records": records}


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Agentic RAG Showcase Eval",
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key, value in payload["metrics"].items():
        lines.append(f"| {key} | {value:.3f} |" if isinstance(value, float) else f"| {key} | {value} |")

    lines.extend(["", "## Cases", ""])
    for case in payload["records"]:
        lines.append(f"### {case['id']} · {case['category']}")
        lines.append("")
        lines.append(f"**Question:** {case['question']}")
        lines.append("")
        lines.append(f"**Focus:** {case.get('difference_focus', '')}")
        lines.append("")
        lines.append("| variant | route | steps | tool | top knowledge | answer preview |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for r in case["variants"]:
            top = "<br>".join(r.get("top_knowledge", []))
            answer = r.get("answer_preview", "").replace("|", "｜")
            lines.append(
                f"| {r['variant']} | {r.get('route','')} | {' -> '.join(r.get('steps', []))} | "
                f"{r.get('tool_called')} / {r.get('tool_ok')} | {top} | {answer} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=0, help="limit cases for a faster smoke run")
    parser.add_argument("--sample-per-category", type=int, default=0, help="stratified sample size per category")
    parser.add_argument("--sample-seed", type=int, default=7)
    parser.add_argument("--testset", type=Path, default=TESTSET)
    parser.add_argument("--timeout-s", type=float, default=90.0, help="per variant/case timeout")
    args = parser.parse_args()

    cases = load_cases(args.testset)
    cases = stratified_sample(cases, per_category=args.sample_per_category, seed=args.sample_seed)
    if args.max_cases:
        cases = cases[:args.max_cases]

    payload = asyncio.run(run_cases(cases, timeout_s=args.timeout_s))
    out_json = RESULTS_DIR / "agentic_showcase.json"
    out_md = RESULTS_DIR / "agentic_showcase.md"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, out_md)
    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
