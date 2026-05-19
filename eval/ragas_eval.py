"""RAGAS-based generation-quality metrics.

We compute faithfulness / answer_relevancy / context_precision per record and
return aggregate means. RAGAS is optional — if not installed, callers receive
zeros and a soft warning. This keeps the project runnable even before students
install the eval-only dependencies.
"""
from __future__ import annotations

from typing import Any


def _build_dataset(records: list[dict]):
    """Build a HuggingFace Dataset compatible with RAGAS."""
    from datasets import Dataset

    rows = []
    for r in records:
        # RAGAS faithfulness / context-precision require a real retrieved
        # context + reference answer. The following categories have neither:
        #   - chitchat: no retrieval at all
        #   - refuse:   meta ground_truth ("应礼貌说明无法回答 + 转人工"），
        #               not a concrete reference answer
        #   - handoff:  canned handoff text, no context, no reference answer
        if r.get("category") in {"chitchat", "refuse", "handoff"}:
            continue
        rows.append({
            "user_input": r["question"],
            "response": r.get("actual_answer", "") or "",
            "retrieved_contexts": r.get("retrieved_contexts", []) or [""],
            "reference": r.get("ground_truth", "") or "",
        })
    return Dataset.from_list(rows)


def run_ragas(records: list[dict]) -> dict[str, Any]:
    """Return {faithfulness, answer_relevancy, context_precision} means."""
    try:
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            faithfulness,
        )
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    except ImportError as exc:
        return {
            "faithfulness": 0.0,
            "answer_relevancy": 0.0,
            "context_precision": 0.0,
            "_warning": f"RAGAS deps missing: {exc}. pip install ragas datasets",
        }

    from app.config import get_settings

    s = get_settings()
    llm = LangchainLLMWrapper(ChatOpenAI(
        model=s.llm_model, api_key=s.openai_api_key, base_url=s.openai_base_url,
        temperature=0.0,
    ))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(
        model=s.embed_model, api_key=s.openai_api_key, base_url=s.openai_base_url,
    ))

    ds = _build_dataset(records)
    if len(ds) == 0:
        return {"faithfulness": 0.0, "answer_relevancy": 0.0, "context_precision": 0.0}

    result = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=llm,
        embeddings=embeddings,
    )

    df = result.to_pandas()
    return {
        "faithfulness": float(df["faithfulness"].mean()),
        "answer_relevancy": float(df["answer_relevancy"].mean()),
        "context_precision": float(df["context_precision"].mean()),
    }
