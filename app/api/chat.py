"""SSE chat endpoint.

We stream two kinds of events to the client:
    event: step   data: {node, input, output, ts}
    event: token  data: {text}
    event: done   data: {answer, citations, end_reason}

This is what powers the right-side "agent thinking" panel and the typewriter
effect on the answer bubble.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import get_graph


router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    variant: str = "full"  # naive | e1 | e2 | full


def _sse(event: str, data) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}


async def _event_stream(question: str, variant: str) -> AsyncIterator[dict]:
    graph = get_graph(variant)
    init_state = {"question": question, "steps": []}

    final_answer = ""
    final_citations: list = []
    end_reason = "answered"

    try:
        async for ev in graph.astream_events(init_state, version="v2"):
            kind = ev.get("event", "")
            name = ev.get("name", "")

            # Node finished -> emit a "step" event
            if kind == "on_chain_end" and name in {
                "router", "retrieve", "grade", "rewrite",
                "tool", "generate", "reflect", "handoff",
            }:
                steps = (ev.get("data", {}) or {}).get("output", {}).get("steps") or []
                for step in steps:
                    yield _sse("step", step)

            # Token streaming for the generate node specifically
            elif kind == "on_chat_model_stream":
                tags = ev.get("tags") or []
                if "generate" in tags:
                    chunk = ev.get("data", {}).get("chunk")
                    text = getattr(chunk, "content", "") if chunk is not None else ""
                    if text:
                        final_answer += text
                        yield _sse("token", {"text": text})

            # Capture final state for "done" event
            elif kind == "on_chain_end" and name == "LangGraph":
                output = ev.get("data", {}).get("output") or {}
                final_answer = output.get("answer", final_answer) or final_answer
                final_citations = output.get("citations") or []
                end_reason = output.get("end_reason") or "answered"
    except Exception as exc:  # noqa: BLE001
        yield _sse("error", {"message": str(exc)})
        return

    yield _sse("done", {
        "answer": final_answer,
        "citations": final_citations,
        "end_reason": end_reason,
    })


@router.post("/chat")
async def chat(req: ChatRequest):
    async def gen():
        async for item in _event_stream(req.question, req.variant):
            yield item
            await asyncio.sleep(0)  # cooperative yield

    return EventSourceResponse(gen())


@router.post("/ingest")
async def ingest(rebuild: bool = True):
    """Trigger a (re)build of the local KB. Useful for demo / dev."""
    from app.ingestion.indexer import build_index

    n = await asyncio.to_thread(build_index, rebuild)
    return {"chunks": n, "rebuilt": rebuild}
