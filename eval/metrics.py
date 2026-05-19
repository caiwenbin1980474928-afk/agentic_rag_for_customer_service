"""Routing / retrieval / latency metrics that don't need RAGAS."""
from __future__ import annotations

from statistics import mean, median
from typing import Any


def route_accuracy(records: list[dict]) -> float:
    """Did the agent take the expected route (kb / tool / chitchat / handoff)?"""
    relevant = [r for r in records if r.get("expected_route")]
    if not relevant:
        return 0.0
    correct = sum(1 for r in relevant if r.get("actual_route") == r["expected_route"])
    return correct / len(relevant)


def tool_call_metrics(records: list[dict]) -> dict[str, float]:
    """Precision / recall for tool invocation."""
    tp = fp = fn = 0
    for r in records:
        expected = r.get("expected_route") == "tool"
        actual = r.get("tool_called", False)
        if expected and actual:
            tp += 1
        elif (not expected) and actual:
            fp += 1
        elif expected and (not actual):
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _hit_indices(expected: list[str], retrieved_sources: list[str]) -> list[int]:
    """Return positions (1-based) of expected sources in retrieved order."""
    hits = []
    for i, src in enumerate(retrieved_sources, 1):
        if src in expected:
            hits.append(i)
    return hits


def hit_at_k(records: list[dict], k: int) -> float:
    """Fraction of records where **at least one** expected source appears in
    top-k retrieved. This is the standard ``hit@k`` (a.k.a. success@k) metric.

    Why ``hit@k`` and not ``recall@k``: our test set has 1–2 expected sources
    per question, and we want a 0/1 per-question score. The classic
    ``recall@k = |hit ∩ expected| / |expected|`` would penalise multi-hop
    questions that retrieve only one of two expected docs, which is not what
    we want to compare here. If you do want to swap in true recall@k, this
    is the single place to change.
    """
    relevant = [r for r in records if r.get("expected_sources")]
    if not relevant:
        return 0.0
    s = 0
    for r in relevant:
        retrieved = r.get("retrieved_sources", [])[:k]
        expected = set(r["expected_sources"])
        if expected & set(retrieved):
            s += 1
    return s / len(relevant)


def mrr(records: list[dict]) -> float:
    """Mean reciprocal rank over records that have expected_sources."""
    relevant = [r for r in records if r.get("expected_sources")]
    if not relevant:
        return 0.0
    total = 0.0
    for r in relevant:
        retrieved = r.get("retrieved_sources", [])
        ranks = _hit_indices(r["expected_sources"], retrieved)
        total += (1.0 / ranks[0]) if ranks else 0.0
    return total / len(relevant)


def latency_stats(records: list[dict]) -> dict[str, float]:
    lat = [r.get("latency_ms", 0.0) for r in records if "latency_ms" in r]
    if not lat:
        return {"p50": 0.0, "p95": 0.0, "mean": 0.0}
    lat_sorted = sorted(lat)
    p50 = median(lat_sorted)
    p95 = lat_sorted[max(0, int(len(lat_sorted) * 0.95) - 1)]
    return {"p50": p50, "p95": p95, "mean": mean(lat_sorted)}


def compute_all(records: list[dict]) -> dict[str, Any]:
    return {
        "n": len(records),
        "route_accuracy": route_accuracy(records),
        "tool": tool_call_metrics(records),
        "hit@3": hit_at_k(records, 3),
        "hit@5": hit_at_k(records, 5),
        "mrr": mrr(records),
        "latency_ms": latency_stats(records),
    }
