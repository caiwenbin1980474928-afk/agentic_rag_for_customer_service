"""Rerank the top-N similarity hits down to top-K with knowledge awareness.

Current implementation is intentionally lightweight (pure Python, no extra
dependency) but does a few useful things on top of raw vector scores:

1. **Dedup near-duplicates** — chunks with identical ``source + section`` and
   the same leading content are collapsed; this fights the common failure
   mode where the top-K is dominated by one paragraph repeated.
2. **Source-diversity penalty** — each additional chunk from a source we
   already picked gets a score penalty, so the final top-K covers multiple
   documents instead of stacking the same one.
3. **Knowledge-type boosts** — safety questions should see safety guardrails,
   process questions should see SOP/procedure chunks, table-like questions
   should see structured tables, and real-time status questions should surface
   tool specs rather than generic policy.

Extension point: swap ``rerank`` with a cross-encoder (e.g.
``BAAI/bge-reranker-v2-m3``) by replacing the body — the public signature and
the call site in ``pipeline.py`` stay the same.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_core.documents import Document

DEFAULT_DIVERSITY_PENALTY = 0.15
REALTIME_ID_RE = re.compile(r"(?<![A-Z0-9])[ALSFC]\d{4,5}(?![A-Z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class QueryProfile:
    raw_query: str = ""
    wants_safety: bool = False
    wants_sop: bool = False
    wants_script: bool = False
    wants_table: bool = False
    wants_tool: bool = False
    wants_escalation: bool = False
    wants_requirements: bool = False
    category: str | None = None


KEYWORDS = {
    "safety": (
        "承诺", "一定", "保证", "必过", "今天到账", "赔付一定", "退款一定",
        "不要编造", "编造", "编一个", "随便写", "造一个", "能不能说",
        "禁止", "风控", "隐私", "手机号", "身份证", "敏感", "透露",
        "泄露", "内部规则", "命中规则", "规避", "绕过", "无凭证",
        "没有凭证", "帮我通过", "通过审核", "安全边界", "要求投诉",
        "找主管", "找经理",
    ),
    "sop": (
        "sop", "流程", "步骤", "怎么处理", "如何处理", "处理流程",
        "操作流程", "怎么办", "工单处理",
    ),
    "script": ("话术", "怎么说", "怎么回复", "回复模板", "客服怎么答", "示例话术"),
    "table": (
        "多久", "几天", "时效", "周期", "费用", "运费", "金额", "条件",
        "支持", "不支持", "地区", "类目", "sla", "优先级", "默认优先级",
        "响应时效",
    ),
    "tool": (
        "查订单", "查询订单", "查一下", "查询", "进度", "状态", "到哪",
        "处理到哪", "工具", "工单号", "订单号", "实时",
    ),
    "escalation": ("转人工", "人工", "投诉", "升级", "主管", "经理", "仲裁", "争议"),
    "requirements": ("需要提供", "准备哪些", "什么材料", "凭证", "照片", "视频", "信息"),
}

CATEGORY_KEYWORDS = {
    "aftersales": (
        "售后", "退货", "退款", "换货", "维修", "保修", "延保", "质检",
        "无理由", "质量问题", "人为损坏", "凭证", "材料",
    ),
    "logistics": (
        "物流", "快递", "包裹", "配送", "发货", "派送", "签收", "运费",
        "冷链", "承运商", "驿站", "快递柜", "破损", "丢失", "改派",
    ),
    "order": (
        "订单", "支付", "扣款", "取消", "地址", "手机号", "尾款", "预售",
        "风控", "审核", "赠品漏发", "会员价",
    ),
    "presales": (
        "商品", "规格", "选购", "库存", "优惠券", "满减", "秒杀", "拼团",
        "会员", "积分", "保价", "价格保护", "企业采购",
    ),
}


def _dedup_key(doc: Document) -> tuple[str, str, str]:
    return (
        doc.metadata.get("source", ""),
        doc.metadata.get("section", ""),
        doc.page_content[:100].strip(),
    )


def profile_query(query: str | None) -> QueryProfile:
    """Classify a user query into retrieval preferences using local heuristics."""
    q = (query or "").lower()

    def has(kind: str) -> bool:
        return any(keyword.lower() in q for keyword in KEYWORDS[kind])

    return QueryProfile(
        raw_query=query or "",
        wants_safety=has("safety"),
        wants_sop=has("sop"),
        wants_script=has("script"),
        wants_table=has("table"),
        wants_tool=bool(REALTIME_ID_RE.search(q)) or has("tool"),
        wants_escalation=has("escalation"),
        wants_requirements=has("requirements"),
        category=_detect_category(q),
    )


def rerank(
    docs_with_scores: list[tuple[Document, float]],
    top_k: int,
    *,
    query: str | None = None,
    diversity_penalty: float = DEFAULT_DIVERSITY_PENALTY,
) -> list[Document]:
    """Return the top-``top_k`` documents after dedup and source-diversity rerank.

    Args:
        docs_with_scores: ``(Document, distance)`` pairs as returned by
            Chroma's ``similarity_search_with_score`` (lower = more similar).
        top_k: Number of documents to keep.
        query: Optional original query for doc_type / chunk_type-aware boosts.
        diversity_penalty: Additive penalty applied each time a source appears
            again. ``0`` disables diversity entirely.
    """
    if not docs_with_scores:
        return []

    seen_keys: set[tuple[str, str, str]] = set()
    unique: list[tuple[Document, float]] = []
    for doc, score in docs_with_scores:
        key = _dedup_key(doc)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append((doc, score))

    profile = profile_query(query)

    source_count: dict[str, int] = {}
    adjusted: list[tuple[Document, float]] = []
    for doc, score in unique:
        src = doc.metadata.get("source", "")
        penalty = diversity_penalty * source_count.get(src, 0)
        adjusted.append((doc, score + penalty + _knowledge_adjustment(doc, profile)))
        source_count[src] = source_count.get(src, 0) + 1

    adjusted.sort(key=lambda x: x[1])
    return [doc for doc, _ in adjusted[:top_k]]


def _knowledge_adjustment(doc: Document, profile: QueryProfile) -> float:
    """Return a negative boost or positive penalty for a candidate document."""
    meta = doc.metadata
    doc_type = str(meta.get("doc_type", "")).lower()
    chunk_type = str(meta.get("chunk_type", "")).lower()
    category = str(meta.get("category", "")).lower()
    title = str(meta.get("title", "")).lower()
    text_head = doc.page_content[:500].lower()
    adjustment = 0.0

    # High-priority governance assets should win when the user is asking about
    # safety boundaries. This prevents a permissive policy chunk from crowding
    # out "do not promise / do not invent" rules.
    if profile.wants_safety:
        adjustment += _boost(doc_type == "safety", 0.55)
        adjustment += _boost(category == "safety", 0.20)
        adjustment += _penalty(doc_type == "policy", 0.08)

    if profile.category:
        adjustment += _boost(category == profile.category, 0.28)
        adjustment += _penalty(
            doc_type in {"policy", "sop", "script"} and category and category != profile.category,
            0.34,
        )

    adjustment += _boost(_title_overlap(title, profile.raw_query), 0.16)

    # Real-time status / lookup questions should surface tool contracts. In the
    # full graph, explicit IDs are routed directly to tools; this makes fallback
    # retrieval and "which tool should I use" questions behave sensibly.
    if profile.wants_tool:
        adjustment += _boost(doc_type == "tool_spec", 0.48)
        adjustment += _boost("工具" in title or "tool" in doc_type, 0.12)
        adjustment += _penalty(doc_type == "policy", 0.08)

    # Process questions need operational SOPs first, but policy procedure chunks
    # are still useful as a customer-safe fallback.
    if profile.wants_sop:
        adjustment += _boost(doc_type == "sop", 0.36)
        adjustment += _boost(doc_type == "sop" and category == profile.category, 0.18)
        adjustment += _penalty(doc_type == "sop" and profile.category and category != profile.category, 0.22)
        adjustment += _boost("procedure" in chunk_type, 0.18)
        adjustment += _boost("流程" in title or "处理" in title, 0.08)

    if profile.wants_script:
        adjustment += _boost(doc_type == "script", 0.45)
        adjustment += _boost(doc_type == "script" and category == profile.category, 0.20)
        adjustment += _penalty(doc_type == "script" and profile.category and category != profile.category, 0.28)
        adjustment += _boost("话术" in title or "话术" in text_head, 0.10)
    else:
        adjustment += _penalty(doc_type == "script", 0.12)

    if profile.wants_table:
        adjustment += _boost(doc_type == "table", 0.50)
        adjustment += _boost(any(word in title for word in ("sla", "时效", "周期", "规则表")), 0.08)
        adjustment += _boost("overview" in chunk_type, 0.05)

    if profile.wants_escalation:
        adjustment += _boost("escalation" in chunk_type, 0.30)
        adjustment += _boost(doc_type == "safety", 0.36)
        adjustment += _boost(doc_type == "safety" and ("转人工" in title or "人工" in text_head or "投诉" in text_head), 0.22)
        adjustment += _boost(doc_type == "sop", 0.12)

    if profile.wants_requirements:
        adjustment += _boost("requirements" in chunk_type, 0.46)
        adjustment += _boost("requirements" in chunk_type and category == profile.category, 0.30)
        adjustment += _penalty("requirements" in chunk_type and profile.category and category != profile.category, 0.50)
        adjustment += _boost("凭证" in text_head or "需要用户提供" in text_head, 0.08)
        adjustment += _boost(any(word in title for word in ("凭证", "退货退款", "申请处理", "售后申请")), 0.24)
        if not profile.wants_sop:
            adjustment += _penalty(doc_type == "sop", 0.16)

    adjustment += _priority_adjustment(meta.get("priority"))
    return adjustment


def _boost(condition: bool, amount: float) -> float:
    return -amount if condition else 0.0


def _penalty(condition: bool, amount: float) -> float:
    return amount if condition else 0.0


def _priority_adjustment(priority: object) -> float:
    try:
        value = float(priority)
    except (TypeError, ValueError):
        return 0.0
    # Keep priority subtle; doc_type intent should dominate.
    return -min(max(value - 50.0, 0.0), 50.0) / 1000.0


def _detect_category(query: str) -> str | None:
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for keyword in keywords if keyword.lower() in query)
    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score > 0 else None


def _title_overlap(title: str, query: str) -> bool:
    """Return true when a meaningful title phrase appears in the query."""
    normalized_title = re.sub(r"\s+", "", title)
    normalized_query = re.sub(r"\s+", "", query.lower())
    if not normalized_title or not normalized_query:
        return False
    if normalized_title in normalized_query or normalized_query in normalized_title:
        return True
    for size in range(5, 1, -1):
        for start in range(0, max(len(normalized_title) - size + 1, 0)):
            phrase = normalized_title[start:start + size]
            if phrase in normalized_query:
                return True
    return False
