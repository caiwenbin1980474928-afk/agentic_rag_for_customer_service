"""Query rewriting for the retrieval layer.

When the first-round retrieval misses, the agent asks this module to produce a
better query. The "when to rewrite" decision belongs to the agent control
flow (``rewrite_node`` in ``app.agent.nodes``); the "how to rewrite" prompt
and LLM call live here.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings

REWRITE_SYSTEM = """你是查询改写专家。用户的原始问题在知识库中检索效果不佳，请将其改写为更利于向量检索的形式。

改写策略：
1. 把口语化表达替换为标准术语（"坏了" → "故障/质量问题"）
2. 展开同义词或近义词（"退" → "退货 退款 退换"）
3. 拆解复合问题，保留核心检索关键词
4. 中文电商客服领域专业表述

只输出改写后的新查询，不要任何解释或多余文字。
"""

REWRITE_USER_TEMPLATE = """原始问题：{question}

已尝试过的查询：{previous}

请输出一个新的、更利于检索的查询："""


def _rewriter_llm(temperature: float = 0.2) -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        model=s.llm_model,
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
        temperature=temperature,
    )


async def rewrite_query(question: str, previous: str | None = None) -> str:
    """Return a fresh query string better suited to vector retrieval.

    Args:
        question: The user's original question (unchanged across rounds).
        previous: The previously tried query, if any, so the LLM avoids
            producing the same rewrite again.
    """
    msg = [
        SystemMessage(content=REWRITE_SYSTEM),
        HumanMessage(content=REWRITE_USER_TEMPLATE.format(
            question=question,
            previous=previous or "（无）",
        )),
    ]
    res = await _rewriter_llm().ainvoke(msg)
    return (res.content or "").strip()
