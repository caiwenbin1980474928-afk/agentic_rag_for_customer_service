---
doc_id: TOOL_COMPLAINT_TICKET_LOOKUP
doc_type: tool_spec
title: 投诉工单查询工具
category: tool
business_stage: 工具调用
version: v2026.06
visibility: internal
priority: 95
---
# 投诉工单查询工具

## 触发条件

用户问题包含C 开头投诉工单号，或明确要求查询实时进度时，必须调用工具，不能只检索知识库。

## 数据来源

`data/mock/complaint_tickets.json`

## 工具用途

查询投诉类型、优先级、专员处理状态和处理摘要。

## 安全边界

工具未命中时，应提示用户核对编号，不要编造状态。工具返回结果与政策文档冲突时，优先说明当前系统状态，并建议人工核实。
