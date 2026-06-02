# Agentic RAG · 电商客服 AI Demo

一个面向课程/答辩演示的 **Agentic RAG 客服系统**。

系统用 LangGraph 编排「路由、工具调用、受治理检索、证据打分、查询改写、答案反思、转人工」等节点，并在前端实时展示 agent 的每一步决策。知识库采用带 `doc_type`、业务阶段、治理边界和自动评测的客服知识资产设计。

默认模型为智谱 GLM：

- LLM：`glm-4-flash`
- Embedding：`embedding-3`
- API 协议：OpenAI-compatible

---

## 1. 系统能力

系统包含以下能力：

- 标准知识库数据包：143 个知识资产文件，索引后 502 个 chunks
- 覆盖售前、售中、售后、物流、发票、投诉、安全边界、工具说明
- 业务结构感知 chunker
- `doc_type` 感知检索与 rerank
- safety 文档前置，控制安全类问题的回答边界
- 生成上下文按 `doc_type` 分区
- 5 类 mock 业务工具：订单、物流工单、售后工单、发票工单、投诉工单
- governed 检索评测集：30 条
- agentic showcase 问题池：80 条
- E0/E1/E2/E3 四组消融对比
- 前端 demo 支持快捷场景和右侧 agent 时间线

评测快照：

```json
{
  "agentic_showcase": {
    "n_cases": 11,
    "n_errors": 0,
    "distinguishing_rate": 1.0,
    "error_rate": 0.0
  },
  "governed_retrieval": {
    "n": 30,
    "pass_rate": 1.0,
    "doc_type_hit": 1.0,
    "top_doc_type_hit": 1.0
  }
}
```

---

## 2. 系统架构

```text
用户问题
  |
  v
router
  |-- handoff -----------------------> human_handoff -> END
  |-- chitchat ----------------------> generate -> END
  |-- tool --------------------------> tool_call -> generate -> reflect? -> END
  |
  '-- kb ----------------------------> retrieve -> grade_docs -> generate -> reflect? -> END
                                      ^             |
                                      |             |
                                      '--- rewrite_query
```

### 四种实验配置

| 版本 | 名称 | 能力 |
| --- | --- | --- |
| E0 | Naive RAG | 纯向量检索 + 生成，不路由、不工具、不 rerank |
| E1 | Router + Tools | 路由、工具调用、受治理检索、转人工 |
| E2 | Self-RAG 检索修正 | E1 + 证据打分 + 查询改写 |
| E3 | Full Agentic | E2 + 答案反思 |

### Router 设计

router 采用 LLM 路由与本地确定性规则结合的设计。高风险和高确定性意图优先由本地规则处理：

- 完整编号：`A1007`、`L2003`、`S3008`、`F4009`、`C5012` 直接进入工具
- 不完整编号：`订单A`、`物流工单L` 不补全，进入工具后返回缺少完整编号
- 转人工/投诉/主管：直接 `handoff`
- 安全越权：如“没有凭证也帮我通过审核”“编一个物流状态”“保证今天到账”，直接进入 safety/KB

这类规则用于约束两个关键边界：

- 不完整编号不触发样例编号补全
- safety 问题不被“售后/物流”等业务关键词误导到工具链

---

## 3. 知识库形态

知识库位于 [data/knowledge](data/knowledge)，采用 **governed customer-service knowledge base** 设计。

### 3.1 知识资产类型

| 目录 | doc_type | 数量 | 用途 |
| --- | --- | ---: | --- |
| `policies/` | `policy` | 120 | 对外可用政策依据，覆盖售前/售中/物流/售后 |
| `sop/` | `sop` | 4 | 内部流程，如售中异常、物流异常、售后争议、投诉处理 |
| `scripts/` | `script` | 4 | 客服话术参考，不作为安全承诺依据 |
| `tables/` | `table` | 4 | 退款周期、物流 SLA、材料清单等结构化规则 |
| `tool_specs/` | `tool_spec` | 5 | 订单/工单查询工具契约 |
| `safety/` | `safety` | 4 | 承诺边界、隐私、风控、强制转人工 |
| `changelog/` | `changelog` | 1 | 版本与生效记录 |

### 3.2 元数据治理

核心文档带有 front matter 元数据：

```yaml
doc_id: POL-AFTERSALES-026
doc_type: policy
category: aftersales
business_stage: aftersales
version: v2026.05
effective_from: 2026-05-01
owner: customer-service-ops
auditor: governance-team
visibility: customer_safe
priority: 80
```

这些字段会进入 chunk metadata，用于：

- 检索过滤
- rerank 加权
- 生成上下文排序
- citation 展示
- 自动评测
- 答辩时解释“为什么召回这类文档”

### 3.3 业务结构感知 chunker

chunker 根据业务文档结构切分：

- 按 markdown 标题识别章节
- 保留 `doc_type`、`category`、`business_stage` 等治理元数据
- 识别 `chunk_type`：`overview`、`procedure`、`requirements`、`escalation`、`reference`
- 对 SOP、材料要求、升级条件、工具说明等内容保持结构完整
- 对超长段落再做有限递归切分，控制 embedding 输入长度

索引路径：

```text
loader -> business-aware chunker -> embedding-3 -> Chroma
```

Chroma collection 中有 502 个 chunks。

### 3.4 doc_type 感知检索/rerank

检索流程位于 [app/retrieval](app/retrieval)：

```text
query
  -> retrieve_with_scores
  -> supplemental_candidates
  -> rerank
  -> safety frontload
  -> top-k docs
```

关键策略：

- 安全类问题优先召回 `safety`
- 流程类问题优先召回 `sop`
- 材料/条件类问题优先召回 `requirements`
- 表格/时效/费用类问题优先召回 `table`
- 实时状态类问题优先走工具，不让普通 policy 编造状态
- 投诉/主管/人工诉求优先 `handoff`

生成上下文会按 doc_type 分区，并强制 safety 在前：

```text
【安全边界】
...

【工具说明】
...

【SOP流程】
...

【结构化规则表】
...

【政策依据】
...

【客服话术】
...
```

这使系统能回答“能做什么”，也能回答“不能承诺什么”。

---

## 4. 工具与 mock 数据

mock 业务数据位于 [data/mock](data/mock)：

| 文件 | 工具 |
| --- | --- |
| `orders.json` | `mock_order_lookup` |
| `logistics_tickets.json` | `mock_logistics_ticket_lookup` |
| `after_sales_tickets.json` | `mock_after_sales_ticket_lookup` |
| `invoice_tickets.json` | `mock_invoice_ticket_lookup` |
| `complaint_tickets.json` | `mock_complaint_ticket_lookup` |

编号规则：

- 订单：`A1001` 这类 A 开头编号
- 物流工单：`L2003` 这类 L 开头编号
- 售后工单：`S3008` 这类 S 开头编号
- 发票工单：`F4009` 这类 F 开头编号
- 投诉工单：`C5012` 这类 C 开头编号

工具层会拒绝不完整编号。例如用户说“我需要看订单A”，系统会提示需要完整订单号或工单号。

---

## 5. 目录结构

```text
.
├── app/
│   ├── agent/
│   │   ├── graph.py           LangGraph 编排与 E0/E1/E2/E3 配置
│   │   ├── nodes.py           router/retrieve/tool/generate/reflect 等节点
│   │   ├── prompts.py         各节点 prompt
│   │   ├── state.py           GraphState
│   │   └── tools.py           mock 工具与转人工话术
│   ├── api/chat.py            SSE 流式聊天接口
│   ├── ingestion/
│   │   ├── loader.py          读取 governed knowledge assets
│   │   ├── chunker.py         业务结构感知 chunker
│   │   ├── embedder.py        embedding 工厂
│   │   ├── vectorstore.py     Chroma 写入/读取
│   │   └── indexer.py         build_index()
│   ├── retrieval/
│   │   ├── retriever.py       Chroma similarity search
│   │   ├── reranker.py        doc_type-aware rerank
│   │   ├── pipeline.py        retrieve_and_rerank()
│   │   └── query_rewriter.py  查询改写
│   ├── ui/index.html          前端 demo
│   └── main.py                FastAPI 入口
├── data/
│   ├── knowledge/             governed 知识库
│   └── mock/                  mock 订单/工单数据
├── eval/
│   ├── testset_governed.jsonl             governed 检索评测集
│   ├── testset_agentic_showcase.jsonl     80 题展示问题池
│   ├── run_governed_retrieval_eval.py     检索治理评测
│   ├── build_agentic_showcase_testset.py  生成 showcase 问题池
│   ├── run_agentic_showcase_eval.py       E0/E1/E2/E3 showcase 对比
│   └── results/
├── scripts/
│   ├── generate_knowledge_assets.py
│   ├── generate_standard_data.py
│   └── ingest.py
├── README.md
└── requirements.txt
```

---

## 6. 快速开始

### 6.1 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6.2 配置环境变量

```bash
cp .env.example .env
```

关键变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 必填 | 智谱或其他兼容服务 API Key |
| `OPENAI_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4/` | OpenAI-compatible endpoint |
| `LLM_MODEL` | `glm-4-flash` | 对话模型 |
| `EMBED_MODEL` | `embedding-3` | 嵌入模型 |
| `DOCS_DIR` | `./data/knowledge` | governed 知识库目录 |
| `TOP_K` | `4` | 最终上下文条数 |
| `MAX_RETRIES` | `3` | grade 失败后的 rewrite 轮数 |

### 6.3 构建索引

```bash
python -m scripts.ingest
```

默认会重建 Chroma 索引，防止重复追加 chunk。

### 6.4 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开：

[http://localhost:8000](http://localhost:8000)

---

## 7. 推荐演示问题

| 场景 | 问题 | 预期差异 |
| --- | --- | --- |
| 工具调用 | `我的订单 A1007 现在是什么状态？` | E0 只能检索，E1+ 调订单工具 |
| 缺编号 | `我需要看订单A` | 不补全为 A1001，提示需要完整编号 |
| 物流工单 | `L2008 的物流停滞有反馈了吗？` | E1+ 调物流工单工具 |
| 投诉升级 | `我要投诉，找你们主管` | E1+ 直接 handoff |
| 安全边界 | `退款一定能今天到账吗？你能保证吗？` | safety 前置，拒绝承诺 |
| 越权审核 | `没有凭证你也帮我通过售后审核吧` | 走 safety/KB，不进工具链 |
| SOP 流程 | `售后质检争议处理流程是什么？` | 召回 SOP，E2+ 有证据打分 |
| 材料凭证 | `退货需要提供什么材料？` | requirements chunk 靠前 |
| 结构化表 | `信用卡退款周期是多久？` | table 优先于普通 policy |
| 风控边界 | `风控拦截的具体规则能告诉我吗？` | 拒绝泄露内部命中规则 |

---

## 8. 评测

### 8.1 Governed 检索评测

用于验证 `doc_type`、`category`、`chunk_type`、工具契约是否被正确召回。

```bash
python -m eval.run_governed_retrieval_eval
```

产物：

- [eval/results/governed_retrieval.json](eval/results/governed_retrieval.json)
- [eval/results/governed_retrieval.md](eval/results/governed_retrieval.md)

参考结果：

```json
{
  "n": 30,
  "pass_rate": 1.0,
  "doc_type_hit": 1.0,
  "category_hit": 1.0,
  "chunk_type_hit": 1.0,
  "top_doc_type_hit": 1.0
}
```

### 8.2 Agentic showcase 对比

用于让 E0/E1/E2/E3 显示出差异。

```bash
python -m eval.run_agentic_showcase_eval --sample-per-category 1 --timeout-s 60
```

跑完整 80 题：

```bash
python -m eval.run_agentic_showcase_eval --timeout-s 60
```

产物：

- [eval/results/agentic_showcase.json](eval/results/agentic_showcase.json)
- [eval/results/agentic_showcase.md](eval/results/agentic_showcase.md)

评测会记录：

- route
- steps
- 是否调用工具
- 工具是否成功
- top knowledge
- answer preview
- latency
- 是否出现错误/超时

---

## 9. 常见问题

**为什么叫 Agentic RAG？**

Agentic RAG 的核心是显式决策链：

- 先判断是否应该检索、查工具、闲聊或转人工
- 实时状态问题走工具，不让知识库编造
- 检索结果可被打分，不足时可改写查询
- 生成后可做忠实度反思
- 投诉/主管/强风险问题可直接转人工

**为什么 safety 要前置？**

客服知识库里很多 policy 会告诉你“流程怎么做”，但安全边界决定“哪些话不能说”。例如退款到账、赔付承诺、风控细节、隐私信息，这些问题必须先看 safety，再看普通政策。

**为什么不能只用客服话术？**

话术适合表达方式，不适合作为事实和合规依据。检索排序优先使用 `safety`、`sop`、`table`、`policy` 等更强依据，`script` 作为表达参考。

**为什么 E2/E3 有时回答和 E1 接近？**

最终话术可能接近，但中间链路不同：

- E1：router + retrieve/tool + generate
- E2：多了 `grade_docs` 和必要时的 `rewrite_query`
- E3：多了 `reflect`

答辩时应展示右侧步骤、top knowledge 和评测报告，不能只看最终句子是否相似。

**为什么有些 SOP 问题比较慢？**

SOP/流程问题通常要检索、生成较长答案；E2/E3 还会多做证据打分和反思。演示时可优先使用 E1 展示速度，用 E3 展示完整 agentic 能力。

---

## 10. 许可

仅用于课程学习、答辩演示和技术研究。
