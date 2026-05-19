"""Compile the LangGraph for different ablation configurations.

AgentConfig lets us toggle agentic features on/off so the four evaluation
groups (E0 Naive ... E3 Full Agentic) reuse the same node implementations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent import nodes
from app.agent.state import GraphState
from app.config import get_settings


def _default_max_retries() -> int:
    """Read from .env so MAX_RETRIES actually takes effect at startup."""
    return get_settings().max_retries


@dataclass(frozen=True)
class AgentConfig:
    enable_router: bool = True
    enable_tools: bool = True
    enable_grade: bool = True
    enable_rewrite: bool = True
    enable_reflect: bool = True
    # rerank is part of "the retrieval pipeline upgrades" — turned OFF for E0
    # so the baseline is truly naive (cosine top-k only). E1+ keep it on.
    enable_rerank: bool = True
    # Default comes from settings (`.env` MAX_RETRIES). Set ``MAX_RETRIES=1``
    # for the demo loop (~10s handoff), set ``MAX_RETRIES=3`` for evaluation
    # to give the rewrite step more chances. Per-variant overrides win.
    max_retries: int = field(default_factory=_default_max_retries)

    @classmethod
    def naive(cls) -> "AgentConfig":
        # True naive RAG: no router, no tools, no grade, no rewrite, no reflect,
        # AND no rerank — just cosine top-k → generate.
        return cls(enable_router=False, enable_tools=False,
                   enable_grade=False, enable_rewrite=False, enable_reflect=False,
                   enable_rerank=False)

    @classmethod
    def with_router_tools(cls) -> "AgentConfig":
        return cls(enable_router=True, enable_tools=True,
                   enable_grade=False, enable_rewrite=False, enable_reflect=False)

    @classmethod
    def with_rewrite(cls) -> "AgentConfig":
        return cls(enable_router=True, enable_tools=True,
                   enable_grade=True, enable_rewrite=True, enable_reflect=False)

    @classmethod
    def full(cls) -> "AgentConfig":
        return cls()


# ---------- Routing helpers ----------------------------------------------

def _after_router(state: dict) -> str:
    return state.get("route", "kb")


def _after_grade(cfg: AgentConfig):
    def _fn(state: dict) -> str:
        grades = state.get("grades") or []
        kept = sum(grades)
        retries = state.get("retries", 0)
        if kept >= 1:
            return "generate"
        if cfg.enable_rewrite and retries < cfg.max_retries:
            return "rewrite"
        return "handoff"

    return _fn


def _after_reflect(cfg: AgentConfig):
    def _fn(state: dict) -> str:
        grounded = state.get("grounded", True)
        retries = state.get("retries", 0)
        if grounded:
            return END
        if cfg.enable_rewrite and retries < cfg.max_retries:
            return "rewrite"
        return END  # accept ungrounded answer rather than loop forever

    return _fn


# ---------- Graph builder ------------------------------------------------

def build_graph(cfg: AgentConfig | None = None):
    cfg = cfg or AgentConfig.full()
    g = StateGraph(GraphState)

    g.add_node("router", nodes.router_node)
    retrieve_impl = nodes.retrieve_node if cfg.enable_rerank else nodes.retrieve_node_plain
    g.add_node("retrieve", retrieve_impl)
    g.add_node("grade", nodes.grade_node)
    g.add_node("rewrite", nodes.rewrite_node)
    g.add_node("tool", nodes.tool_node)
    g.add_node("generate", nodes.generate_node)
    g.add_node("reflect", nodes.reflect_node)
    g.add_node("handoff", nodes.handoff_node)

    # entry
    if cfg.enable_router:
        g.add_edge(START, "router")
        routes: dict[str, str] = {
            "kb": "retrieve",
            "chitchat": "generate",
            "tool": "tool" if cfg.enable_tools else "retrieve",
            "handoff": "handoff",
        }
        g.add_conditional_edges("router", _after_router, routes)
    else:
        g.add_edge(START, "retrieve")

    # tool -> generate (tool result fed into answer)
    g.add_edge("tool", "generate")

    # retrieve -> grade? -> rewrite? loop
    if cfg.enable_grade:
        g.add_edge("retrieve", "grade")
        g.add_conditional_edges("grade", _after_grade(cfg), {
            "generate": "generate",
            "rewrite": "rewrite",
            "handoff": "handoff",
        })
        g.add_edge("rewrite", "retrieve")
    else:
        g.add_edge("retrieve", "generate")

    # generate -> reflect? -> END
    if cfg.enable_reflect:
        g.add_edge("generate", "reflect")
        g.add_conditional_edges("reflect", _after_reflect(cfg), {
            "rewrite": "rewrite",
            END: END,
        })
    else:
        g.add_edge("generate", END)

    g.add_edge("handoff", END)

    return g.compile()


@lru_cache(maxsize=4)
def get_graph(name: str = "full"):
    """Return a compiled graph by ablation name: naive / e1 / e2 / full.

    Cached because LangGraph compilation is not free (~50-200ms). If you
    change ``.env`` (e.g. ``MAX_RETRIES``) and want the new value picked up
    without restarting the process, call :func:`clear_graph_cache` first.
    """
    cfg_map = {
        "naive": AgentConfig.naive(),
        "e1": AgentConfig.with_router_tools(),
        "e2": AgentConfig.with_rewrite(),
        "full": AgentConfig.full(),
    }
    if name not in cfg_map:
        raise ValueError(f"Unknown agent variant: {name}")
    return build_graph(cfg_map[name])


def clear_graph_cache() -> None:
    """Drop all cached compiled graphs so the next ``get_graph`` call rebuilds
    from current ``.env`` settings. Useful during local development /
    notebook sessions when iterating on ``MAX_RETRIES`` etc.
    """
    get_graph.cache_clear()
