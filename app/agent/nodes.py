"""LangGraph node implementations.

Each node:
1. Mutates the shared state
2. Appends one structured "step" record so the UI thinking panel and the
   evaluation harness can both reconstruct what the agent did

Nodes are pure async functions; the streaming LLM token events are surfaced
separately by the API layer via astream_events("v2").
"""
from __future__ import annotations

import asyncio
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
    mock_after_sales_ticket_lookup,
    mock_business_lookup,
    mock_complaint_ticket_lookup,
    mock_invoice_ticket_lookup,
    mock_logistics_ticket_lookup,
    mock_order_lookup,
    tool_name_for_id,
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
        timeout=30,
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
    tool_id: str | None = None


BUSINESS_ID_RE = re.compile(r"(?<![A-Z0-9])([ALSFC]\d{4,5})(?![A-Z0-9])", re.IGNORECASE)
BUSINESS_ID_FULL_RE = re.compile(r"[ALSFC]\d{4,5}", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*?\}")
_VALID_ROUTES = {"tool", "kb", "chitchat", "handoff"}
_PARTIAL_BUSINESS_ID_RE = re.compile(r"(?<![A-Z0-9])([ALSFC])(?:\d{0,3})?(?![A-Z0-9])", re.IGNORECASE)

_HANDOFF_KEYWORDS = (
    "转人工", "转客服", "人工客服", "找客服", "找你们主管", "找主管",
    "要投诉", "投诉升级", "监管投诉", "不想和机器人", "不想跟机器人",
    "专员回电", "主管马上联系", "开投诉工单",
)
_SAFETY_PATTERNS = (
    re.compile(r"(没有|无|没).{0,6}(凭证|材料).{0,12}(通过|审核|放行|批准)"),
    re.compile(r"(帮我|你).{0,8}(编|编造|随便写|造).{0,12}(订单|物流|状态|工单|签收|丢件)"),
    re.compile(r"(承诺|保证|一定|100%).{0,10}(退款|到账|赔|补偿|通过|成功)"),
    re.compile(r"(退款|赔付|补偿).{0,10}(承诺|保证|一定|100%)"),
    re.compile(r"(绕过|规避|避开).{0,8}(风控|审核|规则)"),
    re.compile(r"(风控|质检).{0,10}(具体规则|内部规则|命中规则|模型|规避方法|判定细节)"),
    re.compile(r"(不是本人|非本人).{0,12}(手机号|地址|隐私|订单信息)"),
    re.compile(r"(完整|全部).{0,6}(手机号|身份证|地址)"),
)
_CHITCHAT_EXACT = {"你好", "您好", "hi", "hello", "在吗", "你能帮我做什么"}


def _extract_business_id(text: str) -> str | None:
    m = BUSINESS_ID_RE.search(text)
    return m.group(1).upper() if m else None


def _extract_business_ids(text: str) -> set[str]:
    return {m.upper() for m in BUSINESS_ID_RE.findall(text or "")}


def _has_partial_business_id(text: str) -> bool:
    """Detect business-id-looking fragments such as ``订单A`` or ``工单L``."""
    normalized = (text or "").upper()
    if _extract_business_id(normalized):
        return False
    if not any(word in text for word in ("订单", "工单", "售后", "物流", "发票", "投诉")):
        return False
    return bool(_PARTIAL_BUSINESS_ID_RE.search(normalized))


def _is_safety_sensitive(question: str) -> bool:
    compact = re.sub(r"\s+", "", question or "")
    return any(pattern.search(compact) for pattern in _SAFETY_PATTERNS)


def _route_by_rules(question: str) -> tuple[RouterDecision, str] | None:
    """Fast deterministic routing for high-confidence or high-risk intents.

    This keeps E1 responsive and prevents policy-violating requests from being
    pulled into a tool path by words like "售后" or "物流".
    """
    q = (question or "").strip()
    compact = re.sub(r"\s+", "", q)

    if any(keyword in compact for keyword in _HANDOFF_KEYWORDS):
        return RouterDecision(route="handoff"), "handoff_keyword"

    if _is_safety_sensitive(q):
        return RouterDecision(route="kb"), "safety_guardrail"

    lookup_id = _extract_business_id(q)
    if lookup_id:
        return RouterDecision(route="tool", tool_id=lookup_id, order_id=lookup_id if lookup_id.startswith("A") else None), "complete_business_id"

    if _has_partial_business_id(q):
        return RouterDecision(route="tool"), "partial_business_id"

    if compact.lower() in _CHITCHAT_EXACT:
        return RouterDecision(route="chitchat"), "simple_chitchat"

    return None


def _valid_user_provided_business_id(candidate: str | None, question: str) -> str | None:
    """Accept an LLM-proposed id only if it appears verbatim in user text.

    Router models sometimes "complete" partial IDs from examples, e.g. turning
    "订单A" into "A1001". Tool calls must never be based on such inferred IDs.
    """
    if not candidate:
        return None
    normalized = candidate.strip().upper()
    if not BUSINESS_ID_FULL_RE.fullmatch(normalized):
        return None
    return normalized if normalized in _extract_business_ids(question) else None


def _extract_order_id(text: str) -> str | None:
    lookup_id = _extract_business_id(text)
    return lookup_id if lookup_id and lookup_id.startswith("A") else None


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

    tool_id = data.get("tool_id") or data.get("ticket_id") or data.get("business_id")
    if isinstance(tool_id, str):
        tool_id = tool_id.strip() or None
        if tool_id and tool_id.lower() in {"null", "none"}:
            tool_id = None
    elif tool_id is not None and not isinstance(tool_id, str):
        tool_id = None

    return RouterDecision(route=route, order_id=order_id, tool_id=tool_id)


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


DOC_TYPE_ORDER = {
    "safety": 0,
    "tool_spec": 1,
    "sop": 2,
    "table": 3,
    "policy": 4,
    "script": 5,
    "changelog": 6,
}

DOC_TYPE_LABELS = {
    "safety": "安全边界",
    "tool_spec": "工具说明",
    "sop": "SOP流程",
    "table": "结构化规则表",
    "policy": "政策依据",
    "script": "客服话术",
    "changelog": "版本记录",
}


def _order_docs_for_context(docs: list[Document]) -> list[Document]:
    """Put governance guardrails before ordinary policy context."""
    return sorted(
        docs,
        key=lambda d: (
            DOC_TYPE_ORDER.get(str(d.metadata.get("doc_type", "policy")), 99),
            -int(str(d.metadata.get("priority", "0") or "0")) if str(d.metadata.get("priority", "")).isdigit() else 0,
            d.metadata.get("title", d.metadata.get("source", "")),
            d.metadata.get("chunk_index", 0),
        ),
    )


def _format_docs(docs: list[Document]) -> str:
    if not docs:
        return "（无）"
    parts: list[str] = []
    current_type = None
    for i, d in enumerate(_order_docs_for_context(docs), 1):
        doc_type = str(d.metadata.get("doc_type", "policy") or "policy")
        if doc_type != current_type:
            current_type = doc_type
            parts.append(f"【{DOC_TYPE_LABELS.get(doc_type, doc_type)}】")
        src = d.metadata.get("source", "unknown")
        title = d.metadata.get("title", "")
        sec = d.metadata.get("section", "")
        version = d.metadata.get("version", "")
        visibility = d.metadata.get("visibility", "")
        meta_bits = [bit for bit in [f"type={doc_type}", f"title={title}" if title else "", f"version={version}" if version else "", f"visibility={visibility}" if visibility else ""] if bit]
        head = f"[{i}] {src}" + (f" §{sec}" if sec else "") + (f" ({', '.join(meta_bits)})" if meta_bits else "")
        parts.append(f"{head}\n{d.page_content.strip()}")
    return "\n\n".join(parts)


def _doc_to_citation(idx: int, d: Document) -> dict[str, Any]:
    return {
        "id": idx,
        "source": d.metadata.get("source", "unknown"),
        "path": d.metadata.get("path", ""),
        "doc_id": d.metadata.get("doc_id", ""),
        "doc_type": d.metadata.get("doc_type", ""),
        "title": d.metadata.get("title", ""),
        "category": d.metadata.get("category", ""),
        "business_stage": d.metadata.get("business_stage", ""),
        "version": d.metadata.get("version", ""),
        "effective_from": d.metadata.get("effective_from", ""),
        "visibility": d.metadata.get("visibility", ""),
        "priority": d.metadata.get("priority", ""),
        "section": d.metadata.get("section", ""),
        "snippet": d.page_content[:200],
    }


def _step(name: str, **payload) -> dict[str, Any]:
    return {"node": name, "ts": time.time(), **payload}


def _doc_step_label(d: Document) -> str:
    doc_type = d.metadata.get("doc_type", "policy")
    title = d.metadata.get("title") or d.metadata.get("source", "unknown")
    chunk_type = d.metadata.get("chunk_type", "")
    suffix = f" / {chunk_type}" if chunk_type else ""
    return f"{doc_type}:{title}{suffix}"


# ---------- Nodes ---------------------------------------------------------

async def router_node(state: dict) -> dict:
    """Decide whether to retrieve, call a tool, or just chitchat."""
    question = state["question"]
    rule = _route_by_rules(question)
    router_source = "rules"
    router_error = None
    if rule:
        decision, router_rule = rule
    else:
        router_rule = "llm"
        msg = [
            SystemMessage(content=prompts.ROUTER_SYSTEM),
            HumanMessage(content=prompts.ROUTER_USER_TEMPLATE.format(question=question)),
        ]
        try:
            res = await asyncio.wait_for(_llm().ainvoke(msg), timeout=8)
            decision = _parse_router_decision(res.content or "")
            router_source = "llm"
        except asyncio.TimeoutError:
            decision = RouterDecision(route="kb")
            router_source = "fallback"
            router_error = "router_timeout_after_8s"
        except Exception as exc:  # noqa: BLE001
            decision = RouterDecision(route="kb")
            router_source = "fallback"
            router_error = f"router_error:{type(exc).__name__}"

    route = decision.route if decision.route in _VALID_ROUTES else "kb"
    lookup_id = (
        _extract_business_id(question)
        or _valid_user_provided_business_id(decision.tool_id, question)
        or _valid_user_provided_business_id(decision.order_id, question)
    )
    if lookup_id and route != "handoff":
        route = "tool"

    tool_name = tool_name_for_id(lookup_id) if route == "tool" else None
    tool_args = {"lookup_id": lookup_id} if lookup_id else {}
    if lookup_id and lookup_id.startswith("A"):
        tool_args["order_id"] = lookup_id

    return {
        "route": route,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "retries": 0,
        "steps": [_step("router", input={"question": question},
                         output={"route": route,
                                  "tool_id": lookup_id,
                                  "tool_name": tool_name,
                                  "source": router_source,
                                  "rule": router_rule,
                                  "error": router_error})],
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
                                  "sources": [d.metadata.get("source") for d in docs],
                                  "knowledge": [_doc_step_label(d) for d in docs]})],
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
                                  "sources": [d.metadata.get("source") for d in docs],
                                  "knowledge": [_doc_step_label(d) for d in docs]})],
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
    """Run a deterministic mock business lookup tool."""
    name = state.get("tool_name") or "mock_business_lookup"
    args = state.get("tool_args") or {}
    if name == "mock_order_lookup":
        order_id = args.get("order_id") or args.get("lookup_id") or _extract_order_id(state["question"]) or ""
        result = mock_order_lookup(order_id)
    elif name == "mock_logistics_ticket_lookup":
        result = mock_logistics_ticket_lookup(args.get("lookup_id") or _extract_business_id(state["question"]) or "")
    elif name == "mock_after_sales_ticket_lookup":
        result = mock_after_sales_ticket_lookup(args.get("lookup_id") or _extract_business_id(state["question"]) or "")
    elif name == "mock_invoice_ticket_lookup":
        result = mock_invoice_ticket_lookup(args.get("lookup_id") or _extract_business_id(state["question"]) or "")
    elif name == "mock_complaint_ticket_lookup":
        result = mock_complaint_ticket_lookup(args.get("lookup_id") or _extract_business_id(state["question"]) or "")
    else:
        result = mock_business_lookup(args.get("lookup_id") or _extract_business_id(state["question"]) or "")
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
        docs = _order_docs_for_context(docs)
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
