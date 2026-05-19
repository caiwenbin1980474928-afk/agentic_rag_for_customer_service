"""Typed state passed between LangGraph nodes."""
from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.documents import Document


Route = Literal["kb", "tool", "chitchat", "handoff"]


class GraphState(TypedDict, total=False):
    # input
    question: str

    # routing
    route: Route
    tool_name: str | None
    tool_args: dict[str, Any]

    # retrieval loop
    rewritten: str | None
    docs: list[Document]
    grades: list[bool]
    retries: int

    # generation
    answer: str
    citations: list[dict[str, Any]]
    tool_result: dict[str, Any] | None

    # reflection
    grounded: bool

    # accumulating timeline used by the right-side thinking panel.
    steps: Annotated[list[dict[str, Any]], add]

    end_reason: str  # "answered" | "handoff"   (handoff 既包含主动转人工，也包含多轮失败兜底)
