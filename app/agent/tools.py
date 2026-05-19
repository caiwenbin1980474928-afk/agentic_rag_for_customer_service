"""Deterministic side-effect helpers used by the LangGraph nodes.

This module owns two things:

* ``mock_order_lookup`` — a fake order-lookup tool that ``tool_node`` calls
  when the router classifies a question as ``route="tool"``. Hard-coded JSON
  lets the demo show "agent decides to call a tool instead of retrieving"
  without needing a real order backend.
* ``HANDOFF_MESSAGE_EXHAUSTED`` / ``HANDOFF_MESSAGE_REQUESTED`` — the two
  canned handoff messages used by ``handoff_node``.

These helpers are deliberately NOT registered as LangChain ``BaseTool``
objects because we want tool invocation to happen via an explicit router →
tool edge in the graph, which keeps the agentic control flow observable in
the right-side timeline.
"""
from __future__ import annotations

from dataclasses import dataclass


MOCK_ORDERS: dict[str, dict] = {
    "A1001": {
        "order_id": "A1001",
        "status": "派送中",
        "carrier": "顺丰速运",
        "tracking_no": "SF1234567890",
        "estimated_arrival": "明天 14:00 前",
        "items": ["无线降噪耳机 x1"],
    },
    "A1002": {
        "order_id": "A1002",
        "status": "已签收",
        "carrier": "京东物流",
        "tracking_no": "JD9988776655",
        "signed_at": "2026-05-16 10:23",
        "items": ["智能手表 x1"],
    },
    "A1003": {
        "order_id": "A1003",
        "status": "已发货",
        "carrier": "顺丰速运",
        "tracking_no": "SF2233445566",
        "estimated_arrival": "3 天内",
        "items": ["蓝牙音箱 x1", "充电器 x1"],
    },
    "A1004": {
        "order_id": "A1004",
        "status": "未发货 (待出库)",
        "carrier": "-",
        "tracking_no": "-",
        "estimated_arrival": "下单后 24 小时内出库",
        "items": ["机械键盘 x1"],
    },
}


@dataclass
class ToolResult:
    name: str
    ok: bool
    data: dict | str


def mock_order_lookup(order_id: str) -> ToolResult:
    """Look up a fake order by id."""
    order_id = (order_id or "").strip().upper()
    if not order_id:
        return ToolResult("mock_order_lookup", False, "缺少订单号")
    record = MOCK_ORDERS.get(order_id)
    if record is None:
        return ToolResult(
            "mock_order_lookup",
            False,
            f"未找到订单 {order_id}。请确认订单号是否正确（示例：A1001 / A1002 / A1003 / A1004）。",
        )
    return ToolResult("mock_order_lookup", True, record)


HANDOFF_MESSAGE_EXHAUSTED = (
    "非常抱歉，您的问题超出了我目前的处理范围，已为您转接人工客服，"
    "客服会在 3 分钟内联系您。您也可以拨打 400-800-1234（9:00–22:00）。"
)

HANDOFF_MESSAGE_REQUESTED = (
    "好的，已为您转接人工客服，客服会在 3 分钟内主动联系您。"
    "如急需处理，也可以直接拨打 400-800-1234（9:00–22:00）。"
)
