# Governed Customer-Service Knowledge

这是项目的受治理客服知识库目录，采用结构化知识资产设计。

知识资产会被 `app/ingestion/loader.py` 读取，再由业务结构感知 chunker 切分为带元数据的 chunks，最终写入 Chroma。索引规模为 143 个资产文件、502 个 chunks。

## Asset Types

| 目录 | doc_type | 数量 | 作用 |
| --- | --- | ---: | --- |
| `policies/` | `policy` | 120 | 对外可用政策依据，覆盖售前、售中、物流、售后 |
| `sop/` | `sop` | 4 | 内部处理流程，例如物流异常、售后争议、投诉处理 |
| `scripts/` | `script` | 4 | 客服话术参考，用于表达方式，不作为事实或合规最高依据 |
| `tables/` | `table` | 4 | 退款周期、物流 SLA、材料清单等结构化规则 |
| `tool_specs/` | `tool_spec` | 5 | 订单/物流/售后/发票/投诉工具调用契约 |
| `safety/` | `safety` | 4 | 承诺边界、隐私身份、风控、强制转人工规则 |
| `changelog/` | `changelog` | 1 | 版本、生效时间和治理记录 |

## Metadata

核心资产包含以下 front matter 字段：

- `doc_id`
- `doc_type`
- `category`
- `business_stage`
- `version`
- `effective_from`
- `owner`
- `auditor`
- `visibility`
- `priority`

这些元数据会进入 chunk metadata，供检索过滤、rerank、生成上下文排序、citation 展示和自动评测使用。

## Chunk Types

chunker 会尽量保留业务结构，并识别以下 `chunk_type`：

- `overview`: 场景定义、适用范围、核心说明
- `procedure`: 内部处理步骤和 SOP 流程
- `requirements`: 材料、凭证、条件和限制
- `escalation`: 转人工、建工单、升级和争议处理
- `reference`: 工具说明、表格、话术、安全规则等参考资产

## Retrieval Governance

检索/rerank 会感知 `doc_type`：

- 安全类问题优先 `safety`
- 流程类问题优先 `sop`
- 材料类问题优先 `requirements`
- 时效/费用/周期类问题优先 `table`
- 实时状态类问题优先工具，不允许普通 `policy` 编造订单或工单状态
- 客服话术 `script` 仅作为表达参考，不抢安全边界和政策依据

生成上下文也会按 doc_type 分区，并将 safety 永远前置。
