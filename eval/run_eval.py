"""Run a single ablation group across the test set and dump JSON results.

Usage:
    python -m eval.run_eval --variant naive
    python -m eval.run_eval --variant e1
    python -m eval.run_eval --variant e2
    python -m eval.run_eval --variant full
    python -m eval.run_eval --all          # run all four sequentially
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.graph import get_graph
from eval.metrics import compute_all
from eval.ragas_eval import run_ragas


TESTSET = ROOT / "eval" / "testset.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

VARIANTS = ["naive", "e1", "e2", "full"]


def _load_testset() -> list[dict]:
    with TESTSET.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def _run_one(variant: str, case: dict) -> dict:
    graph = get_graph(variant)
    init_state = {"question": case["question"], "steps": []}
    t0 = time.perf_counter()
    try:
        final = await graph.ainvoke(init_state)
        latency_ms = (time.perf_counter() - t0) * 1000.0
    except Exception as exc:  # noqa: BLE001
        return {
            **case,
            "variant": variant,
            "error": str(exc),
            "actual_answer": "",
            "actual_route": "error",
            "retrieved_sources": [],
            "retrieved_contexts": [],
            "tool_called": False,
            "latency_ms": (time.perf_counter() - t0) * 1000.0,
        }

    docs = final.get("docs") or []
    retrieved_sources = [d.metadata.get("source", "") for d in docs]
    retrieved_contexts = [d.page_content for d in docs]
    steps = final.get("steps") or []

    actual_route = final.get("route") or (
        "kb" if any(s.get("node") == "retrieve" for s in steps) else "chitchat"
    )
    tool_called = any(s.get("node") == "tool_call" for s in steps)

    return {
        **case,
        "variant": variant,
        "actual_answer": final.get("answer", "") or "",
        "actual_route": actual_route,
        "retrieved_sources": retrieved_sources,
        "retrieved_contexts": retrieved_contexts[:3],
        "tool_called": tool_called,
        "n_steps": len(steps),
        "latency_ms": latency_ms,
        "end_reason": final.get("end_reason", "answered"),
    }


async def run_variant(variant: str, *, ragas: bool = True) -> dict:
    print(f"[eval] === running variant {variant} ===")
    cases = _load_testset()
    records: list[dict] = []
    for i, case in enumerate(cases, 1):
        rec = await _run_one(variant, case)
        records.append(rec)
        print(f"  [{i:>2}/{len(cases)}] {case['question'][:32]} ... {rec.get('actual_route'):8s}  {rec['latency_ms']:.0f}ms")

    metrics = compute_all(records)
    if ragas:
        print("[eval] computing RAGAS metrics (this calls the LLM, may take a while)...")
        metrics["ragas"] = run_ragas(records)
    else:
        metrics["ragas"] = {"skipped": True}

    payload = {"variant": variant, "metrics": metrics, "records": records}
    out_path = RESULTS_DIR / f"{variant}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[eval] wrote {out_path}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=VARIANTS, help="single variant to run")
    parser.add_argument("--all", action="store_true", help="run all four variants")
    parser.add_argument("--no-ragas", action="store_true", help="skip RAGAS (faster)")
    args = parser.parse_args()

    variants = VARIANTS if args.all else [args.variant or "full"]

    async def _go():
        for v in variants:
            await run_variant(v, ragas=not args.no_ragas)

    asyncio.run(_go())


if __name__ == "__main__":
    main()
