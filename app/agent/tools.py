"""Deterministic side-effect helpers used by the LangGraph nodes.

The mock lookup helpers read repo-local JSON records under ``data/mock``.
They are deliberately NOT registered as LangChain ``BaseTool`` objects because
we want tool invocation to happen via an explicit router → tool edge in the
graph, which keeps the agentic control flow observable in the UI timeline.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class ToolResult:
    name: str
    ok: bool
    data: dict | str


ROOT = Path(__file__).resolve().parents[2]
MOCK_DIR = ROOT / "data" / "mock"
BUSINESS_ID_FULL_RE = re.compile(r"[ALSFC]\d{4,5}", re.IGNORECASE)

TOOL_SPECS: dict[str, dict[str, str]] = {
    "A": {
        "name": "mock_order_lookup",
        "file": "orders.json",
        "key": "order_id",
        "label": "订单",
        "examples": "A1001 / A1032",
    },
    "L": {
        "name": "mock_logistics_ticket_lookup",
        "file": "logistics_tickets.json",
        "key": "ticket_id",
        "label": "物流工单",
        "examples": "L2003 / L2016",
    },
    "S": {
        "name": "mock_after_sales_ticket_lookup",
        "file": "after_sales_tickets.json",
        "key": "ticket_id",
        "label": "售后工单",
        "examples": "S3008 / S3021",
    },
    "F": {
        "name": "mock_invoice_ticket_lookup",
        "file": "invoice_tickets.json",
        "key": "ticket_id",
        "label": "发票工单",
        "examples": "F4009",
    },
    "C": {
        "name": "mock_complaint_ticket_lookup",
        "file": "complaint_tickets.json",
        "key": "ticket_id",
        "label": "投诉工单",
        "examples": "C5012",
    },
}


@lru_cache(maxsize=8)
def _load_records(filename: str, key: str) -> dict[str, dict]:
    path = MOCK_DIR / filename
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row.get(key, "")).upper(): row for row in rows if row.get(key)}


def _lookup_by_prefix(lookup_id: str, *, expected_prefix: str | None = None) -> ToolResult:
    lookup_id = (lookup_id or "").strip().upper()
    if not lookup_id:
        return ToolResult("mock_business_lookup", False, "缺少订单号或工单号")
    if not BUSINESS_ID_FULL_RE.fullmatch(lookup_id):
        return ToolResult(
            "mock_business_lookup",
            False,
            f"编号 {lookup_id} 不完整。请提供完整订单号或工单号，例如 A1007、L2003、S3008。",
        )

    prefix = expected_prefix or lookup_id[:1]
    spec = TOOL_SPECS.get(prefix)
    if spec is None:
        return ToolResult(
            "mock_business_lookup",
            False,
            f"暂不支持编号 {lookup_id}。支持订单 A、物流工单 L、售后工单 S、发票工单 F、投诉工单 C。",
        )

    records = _load_records(spec["file"], spec["key"])
    record = records.get(lookup_id)
    if record is None:
        return ToolResult(
            spec["name"],
            False,
            f"未找到{spec['label']} {lookup_id}。请确认编号是否正确（示例：{spec['examples']}）。",
        )
    return ToolResult(spec["name"], True, record)


def mock_order_lookup(order_id: str) -> ToolResult:
    """Look up a mock order by id."""
    return _lookup_by_prefix(order_id, expected_prefix="A")


def mock_logistics_ticket_lookup(ticket_id: str) -> ToolResult:
    """Look up a mock logistics ticket by id."""
    return _lookup_by_prefix(ticket_id, expected_prefix="L")


def mock_after_sales_ticket_lookup(ticket_id: str) -> ToolResult:
    """Look up a mock after-sales ticket by id."""
    return _lookup_by_prefix(ticket_id, expected_prefix="S")


def mock_invoice_ticket_lookup(ticket_id: str) -> ToolResult:
    """Look up a mock invoice ticket by id."""
    return _lookup_by_prefix(ticket_id, expected_prefix="F")


def mock_complaint_ticket_lookup(ticket_id: str) -> ToolResult:
    """Look up a mock complaint ticket by id."""
    return _lookup_by_prefix(ticket_id, expected_prefix="C")


def mock_business_lookup(lookup_id: str) -> ToolResult:
    """Dispatch to the matching mock lookup by identifier prefix."""
    return _lookup_by_prefix(lookup_id)


def tool_name_for_id(lookup_id: str | None) -> str | None:
    """Return the deterministic tool name for an order/ticket id."""
    if not lookup_id:
        return None
    normalized = lookup_id.strip().upper()
    if not BUSINESS_ID_FULL_RE.fullmatch(normalized):
        return None
    spec = TOOL_SPECS.get(normalized[:1])
    return spec["name"] if spec else None


HANDOFF_MESSAGE_EXHAUSTED = (
    "非常抱歉，您的问题超出了我目前的处理范围，已为您转接人工客服，"
    "客服会在 3 分钟内联系您。您也可以拨打 400-800-1234（9:00–22:00）。"
)

HANDOFF_MESSAGE_REQUESTED = (
    "好的，已为您转接人工客服，客服会在 3 分钟内主动联系您。"
    "如急需处理，也可以直接拨打 400-800-1234（9:00–22:00）。"
)
