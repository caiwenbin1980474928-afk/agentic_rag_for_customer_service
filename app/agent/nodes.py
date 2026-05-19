"""LangGraph node implementations.

Each node:
1. Mutates the shared state
2. Appends one structured "step" record so the UI thinking panel and the
   evaluation harness can both reconstruct what the agent did

Nodes are pure async functions; the streaming LLM token events are surfaced
separately by the API layer via astream_events("v2").
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent import prompts
from app.agent.tools import (
    mock_order_lookup,
    HANDOFF_MESSAGE_EXHAUSTED,
    HANDOFF_MESSAGE_REQUESTED,
)
from app.config import get_settings
from app.retrieval.pipeline import retrieve_and_rerank
from app.retrieval.query_rewriter import rewrite_query
from app.retrieval.retriever import retrieve_with_scores


# ---------- LLM factory ---------------------------------------------------

def _llm(temperature: float = 0.0, streaming: bool = False, tags: list[str] | None = None) -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        model=s.llm_model,
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
        temperature=temperature,
        streaming=streaming,
        tags=tags or [],
    )


# ---------- Output parsing (provider-agnostic) ---------------------------
#
# We deliberately avoid ``with_structured_output()`` because not every
# OpenAI-compatible provider (e.g. GLM-4 family) implements tool calling
# perfectly. Instead we ask the model for JSON / yes-no in the prompt and
# parse it defensively here.

@dataclass
class RouterDecision:
    route: str
    order_id: str | None = None


ORDER_ID_RE = re.compile(r"\b([A-Z]\d{3,5})\b", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*?\}")
_VALID_ROUTES = {"tool", "kb", "chitchat", "handoff"}


def _extract_order_id(text: str) -> str | None:
    m = ORDER_ID_RE.search(text)
    return m.group(1).upper() if m else None


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _parse_router_decision(text: str) -> RouterDecision:
    """Best-effort parse of router LLM output. Falls back to ``route='kb'``."""
    cleaned = _strip_code_fence(text or "")

    data: dict[str, Any] = {}
    try:
        data = json.loads(cleaned)
    except Exception:
        m = _JSON_OBJECT_RE.search(cleaned)
        if m:
            try:
                data = json.loads(m.group())
            except Exception:
                data = {}

    route = str(data.get("route", "")).strip().lower()
    if route not in _VALID_ROUTES:
        lower = cleaned.lower()
        if "handoff" in lower:
            route = "handoff"
        elif "tool" in lower:
            route = "tool"
        elif "chitchat" in lower:
            route = "chitchat"
        else:
            route = "kb"

    order_id = data.get("order_id")
    if isinstance(order_id, str):
        order_id = order_id.strip() or None
        if order_id and order_id.lower() in {"null", "none"}:
            order_id = None
    elif order_id is not None and not isinstance(order_id, str):
        order_id = None

    return RouterDecision(route=route, order_id=order_id)


def _parse_yes_no(text: str, *, default: bool = False) -> bool:
    """Best-effort yes/no parser tolerating JSON / quotes / explanations."""
    s = (text or "").strip().lower().strip('"').strip("'")
    if not s:
        return default
    if s.startswith("y") or s.startswith("是"):
        return True
    if s.startswith("n") or s.startswith("否"):
        return False
    m = re.search(r'"verdict"\s*:\s*"?(yes|no)', s)
    if m:
        return m.group(1) == "yes"
    if "yes" in s[:20]:
        return True
    if "no" in s[:20]:
        return False
    return default


def _format_docs(docs: list[Document]) -> str:
    if not docs:
        return "（无）"
    parts = []
    for i, d in enumerate(docs, 1):
        src = d.metadata.get("source", "unknown")
        sec = d.metadata.get("section", "")
        head = f"[{i}] {src}" + (f" §{sec}" if sec else "")
        parts.append(f"{head}\n{d.page_content.strip()}")
    return "\n\n".join(parts)


def _doc_to_citation(idx: int, d: Document) -> dict[str, Any]:
    return {
        "id": idx,
        "source": d.metadata.get("source", "unknown"),
        "section": d.metadata.get("section", ""),
        "snippet": d.page_content[:200],
    }


def _step(name: str, **payload) -> dict[str, Any]:
    return {"node": name, "ts": time.time(), **payload}


# ---------- Nodes ---------------------------------------------------------

async def router_node(state: dict) -> dict:
    """Decide whether to retrieve, call a tool, or just chitchat."""
    question = state["question"]
    msg = [
        SystemMessage(content=prompts.ROUTER_SYSTEM),
        HumanMessage(content=prompts.ROUTER_USER_TEMPLATE.format(question=question)),
    ]
    res = await _llm().ainvoke(msg)
    decision = _parse_router_decision(res.content or "")

    route = decision.route if decision.route in _VALID_ROUTES else "kb"
    order_id = decision.order_id or _extract_order_id(question)
    tool_args = {"order_id": order_id} if order_id else {}

    return {
        "route": route,
        "tool_name": "mock_order_lookup" if route == "tool" else None,
        "tool_args": tool_args,
        "retries": 0,
        "steps": [_step("router", input={"question": question},
                         output={"route": route, "order_id": order_id})],
    }


async def retrieve_node(state: dict) -> dict:
    """Vector search the KB with the current (possibly rewritten) query.

    Delegates to ``retrieve_and_rerank`` so the agent stays agnostic of the
    underlying retrieve → rerank pipeline. Used by E1+ / E2 / E3.
    """
    q = state.get("rewritten") or state["question"]
    docs = retrieve_and_rerank(q)
    return {
        "docs": docs,
        "steps": [_step("retrieve",
                         input={"query": q, "round": state.get("retries", 0) + 1,
                                "rerank": True},
                         output={"n_docs": len(docs),
                                  "sources": [d.metadata.get("source") for d in docs]})],
    }


async def retrieve_node_plain(state: dict) -> dict:
    """Naive cosine top-k, no rerank — used by the E0 baseline to provide a
    truly naive retrieval reference for the ablation comparison.
    """
    q = state.get("rewritten") or state["question"]
    settings = get_settings()
    pairs = retrieve_with_scores(q, k=settings.top_k)
    docs = [d for d, _ in pairs]
    return {
        "docs": docs,
        "steps": [_step("retrieve",
                         input={"query": q, "round": state.get("retries", 0) + 1,
                                "rerank": False},
                         output={"n_docs": len(docs),
                                  "sources": [d.metadata.get("source") for d in docs]})],
    }


async def grade_node(state: dict) -> dict:
    """Yes/no relevance check for each retrieved doc."""
    question = state["question"]
    docs: list[Document] = state.get("docs", [])
    llm = _llm()

    grades: list[bool] = []
    for d in docs:
        msg = [
            SystemMessage(content=prompts.GRADE_SYSTEM),
            HumanMessage(content=prompts.GRADE_USER_TEMPLATE.format(
                question=question, doc=d.page_content[:1200])),
        ]
        try:
            res = await llm.ainvoke(msg)
            grades.append(_parse_yes_no(res.content or "", default=False))
        except Exception:
            grades.append(False)

    return {
        "grades": grades,
        "steps": [_step("grade_docs",
                         input={"n_docs": len(docs)},
                         output={"grades": grades,
                                  "kept": sum(grades)})],
    }


async def rewrite_node(state: dict) -> dict:
    """Produce a better query for the next retrieval round.

    The actual prompt + LLM call lives in ``app.retrieval.query_rewriter``;
    this node only owns the control-flow concern (tracking retries).
    """
    question = state["question"]
    previous = state.get("rewritten")
    rewritten = await rewrite_query(question, previous=previous)
    return {
        "rewritten": rewritten,
        "retries": state.get("retries", 0) + 1,
        "steps": [_step("rewrite_query",
                         input={"original": question, "previous": previous or "（无）"},
                         output={"rewritten": rewritten})],
    }


async def tool_node(state: dict) -> dict:
    """Run a deterministic tool (currently only mock_order_lookup)."""
    name = state.get("tool_name") or "mock_order_lookup"
    args = state.get("tool_args") or {}
    if name == "mock_order_lookup":
        order_id = args.get("order_id") or _extract_order_id(state["question"]) or ""
        result = mock_order_lookup(order_id)
    else:
        result = mock_order_lookup("")  # graceful fallback
    payload: dict[str, Any] = {"ok": result.ok, "data": result.data}
    return {
        "tool_result": payload,
        "steps": [_step("tool_call",
                         input={"name": name, "args": args},
                         output=payload)],
    }


async def generate_node(state: dict) -> dict:
    """Final answer generation. Tagged so token streaming can be captured.

    Picks a different prompt depending on ``state['route']``:
    - chitchat → natural, no-context CHITCHAT_SYSTEM
    - kb / tool → strict GENERATE_SYSTEM that grounds on docs + tool output
    """
    question = state["question"]
    docs: list[Document] = state.get("docs", [])
    grades = state.get("grades")
    if grades:
        docs = [d for d, ok in zip(docs, grades) if ok] or docs

    tool_result = state.get("tool_result")
    route = state.get("route") or ("tool" if tool_result else "kb")

    if route == "chitchat" and not tool_result and not docs:
        msg = [
            SystemMessage(content=prompts.CHITCHAT_SYSTEM),
            HumanMessage(content=prompts.CHITCHAT_USER_TEMPLATE.format(question=question)),
        ]
        llm = _llm(temperature=0.6, streaming=True, tags=["generate"])
    else:
        tool_text = (
            "（无）" if not tool_result
            else f"工具={state.get('tool_name')} 是否成功={tool_result['ok']} 结果={tool_result['data']}"
        )
        context = _format_docs(docs)
        msg = [
            SystemMessage(content=prompts.GENERATE_SYSTEM),
            HumanMessage(content=prompts.GENERATE_USER_TEMPLATE.format(
                question=question, context=context, tool_result=tool_text)),
        ]
        llm = _llm(temperature=0.3, streaming=True, tags=["generate"])

    res = await llm.ainvoke(msg)
    answer = res.content.strip()

    citations = [_doc_to_citation(i + 1, d) for i, d in enumerate(docs)]
    return {
        "answer": answer,
        "citations": citations,
        "steps": [_step("generate",
                         input={"route": route,
                                "n_context_docs": len(docs),
                                "has_tool_result": tool_result is not None},
                         output={"answer_preview": answer[:120]})],
    }


async def reflect_node(state: dict) -> dict:
    """Hallucination / faithfulness check."""
    docs: list[Document] = state.get("docs", [])
    answer = state.get("answer", "")
    if not docs or not answer:
        return {
            "grounded": True,
            "steps": [_step("reflect",
                             input={"skipped": True}, output={"grounded": True})],
        }

    msg = [
        SystemMessage(content=prompts.REFLECT_SYSTEM),
        HumanMessage(content=prompts.REFLECT_USER_TEMPLATE.format(
            context=_format_docs(docs)[:3000], answer=answer)),
    ]
    try:
        res = await _llm().ainvoke(msg)
        grounded = _parse_yes_no(res.content or "", default=True)
    except Exception:
        grounded = True

    return {
        "grounded": grounded,
        "steps": [_step("reflect",
                         input={"answer_len": len(answer)},
                         output={"grounded": grounded})],
    }


async def handoff_node(state: dict) -> dict:
    """Transfer to human. Two trigger paths:

    1. **User-requested** (router classified as ``handoff``) → polite acknowledgement
    2. **Exhausted** (grade failed too many rounds) → apologetic out-of-scope message

    Both surface the 400 phone line and the 3-minute callback SLA.
    """
    is_user_requested = state.get("route") == "handoff"
    message = HANDOFF_MESSAGE_REQUESTED if is_user_requested else HANDOFF_MESSAGE_EXHAUSTED
    reason = "user_requested" if is_user_requested else "retries_exhausted"
    return {
        "answer": message,
        "citations": [],
        "end_reason": "handoff",
        "steps": [_step("human_handoff",
                         input={"reason": reason,
                                "retries": state.get("retries", 0)},
                         output={"message": message})],
    }
