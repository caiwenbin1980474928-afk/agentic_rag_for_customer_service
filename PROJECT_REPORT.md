# 基于 Agentic RAG 的电商客服智能问答系统项目报告

## 摘要

本项目实现了一个面向电商客服场景的 Agentic RAG 智能问答系统。系统不再采用固定的“检索知识库 -> 生成回答”流程，而是通过 LangGraph 显式编排客服 Agent，使其能够根据用户问题动态选择知识库检索、业务工具查询、查询改写、答案反思或人工兜底。

当前版本的系统覆盖售前咨询、售中订单、物流配送、售后服务、安全边界、发票和投诉等客服场景。知识库采用 governed knowledge assets 设计：当前 `data/knowledge` 中被 loader 实际读取的资产为 142 个，索引后形成 502 个 chunks；每个资产和 chunk 保留 `doc_type`、`category`、`business_stage`、`visibility`、`priority` 等治理元数据。系统还提供 5 类 mock 业务工具，分别用于订单、物流工单、售后工单、发票工单和投诉工单查询。

项目同时提供 FastAPI 后端、单页前端、SSE 流式输出、本地 Chroma 向量库、E0/E1/E2/E3 四组消融配置，以及 governed retrieval、agentic showcase、gradient eval 等评测脚本。它适合作为课程报告、技术演示和 Agentic RAG 原型验证项目。

---

## 1. 项目名称

中文名称：

**基于 Agentic RAG 的电商客服智能问答系统**

英文名称：

**An E-commerce Customer Service Intelligent Q&A System Based on Agentic RAG**

项目简称：

**Agentic RAG 客服 AI Demo**

---

## 2. 项目背景与目标

### 2.1 背景

电商客服问题通常具有以下特点：

- 用户表达口语化，例如“耳机坏了能退吗”“快递三天没动了怎么办”。
- 一个问题可能同时涉及政策、流程、材料、时效和具体订单状态。
- 实时状态类问题不能靠知识库猜测，必须调用订单或工单系统。
- 客服回答需要遵守业务边界，不能承诺必退、必赔、必达或泄露风控细节。
- 用户可能随时要求转人工或投诉升级。

朴素 RAG 的流程通常是：

```text
用户问题 -> 检索知识库 -> 大模型生成回答
```

这种固定流程难以处理实时查询、人工升级、安全边界和检索失败后的自我修正。因此，本项目采用 Agentic RAG 架构，把客服问答系统升级为一个可决策、可行动、可观察、可评测的客服 Agent。

### 2.2 业务目标

- 支持售前、售中、物流、售后、发票、投诉等客服问答。
- 支持订单和各类工单实时状态查询。
- 对转人工、投诉、主管介入等诉求进行快速路由。
- 对退款承诺、赔付承诺、无凭证审核、隐私和风控规则等高风险问题进行安全约束。
- 在资料不足或多轮处理后仍无法可靠回答时，转人工兜底。

### 2.3 技术目标

- 使用 LangGraph 显式编排 Agent 状态图。
- 使用 LangChain + Chroma 构建本地 RAG 知识库。
- 使用 OpenAI-compatible 协议接入智谱 GLM 或其他模型服务。
- 使用 SSE 实现 token 流和 Agent 步骤流。
- 通过 E0/E1/E2/E3 消融实验展示各 Agentic 组件的作用。
- 通过 governed retrieval 评测验证知识治理能力。

---

## 3. 系统总体架构

```text
用户浏览器
  |
  | HTTP + SSE
  v
FastAPI 后端
  |
  | /api/chat
  v
LangGraph Agent
  |-- router
  |-- retrieve / grade / rewrite
  |-- tool_call
  |-- generate
  |-- reflect
  '-- human_handoff
  |
  +--> Chroma 向量库
  +--> mock 业务工具
```

核心目录：

| 路径 | 作用 |
| --- | --- |
| `app/main.py` | FastAPI 入口、健康检查、前端页面挂载 |
| `app/api/chat.py` | `/api/chat` SSE 聊天接口和 `/api/ingest` 索引接口 |
| `app/agent/graph.py` | LangGraph 编排和四组实验配置 |
| `app/agent/nodes.py` | router、retrieve、grade、rewrite、tool、generate、reflect、handoff 节点 |
| `app/agent/tools.py` | mock 业务工具和转人工话术 |
| `app/ingestion/` | 文档加载、切分、Embedding、Chroma 写入 |
| `app/retrieval/` | Chroma 检索、doc_type 感知 rerank、查询改写 |
| `app/ui/index.html` | 单页演示前端 |
| `data/knowledge/` | 当前正式 governed 知识库 |
| `data/mock/` | 订单和工单 mock 数据 |
| `eval/` | 评测集、评测脚本和结果文件 |

---

## 4. Agent 工作流

当前完整版本 `full` 的流程如下：

```text
用户问题
  |
  v
router
  |-- handoff -----------------------> human_handoff -> END
  |-- chitchat ----------------------> generate -> reflect -> END
  |-- tool --------------------------> tool_call -> generate -> reflect -> END
  |
  '-- kb ----------------------------> retrieve -> grade_docs -> generate -> reflect -> END
                                      ^             |
                                      |             |
                                      '--- rewrite_query
```

系统通过 `GraphState` 在节点之间传递状态，关键字段包括：

| 字段 | 含义 |
| --- | --- |
| `question` | 用户原始问题 |
| `route` | `kb`、`tool`、`chitchat`、`handoff` |
| `tool_name` / `tool_args` | 工具名称与参数 |
| `docs` | 检索到的文档片段 |
| `grades` | 文档相关性判断 |
| `rewritten` | 改写后的查询 |
| `tool_result` | 工具查询结果 |
| `answer` | 最终回答 |
| `citations` | 引用来源 |
| `grounded` | 反思节点的忠实度判断 |
| `steps` | 前端时间线和评测记录使用的步骤列表 |
| `end_reason` | `answered` 或 `handoff` |

---

## 5. 四组消融配置

项目在 `app/agent/graph.py` 中定义四组 Agent 变体：

| 变体 | 名称 | 能力 |
| --- | --- | --- |
| `naive` | E0 Naive RAG | 纯向量 top-k 检索 + 生成；无路由、无工具、无打分、无改写、无反思、无 rerank |
| `e1` | E1 Router + Tools | 增加 router、mock 工具、handoff 和 doc_type-aware rerank |
| `e2` | E2 Self-RAG 检索修正 | 在 E1 基础上增加 `grade_docs` 和 `rewrite_query` |
| `full` | E3 Full Agentic | 在 E2 基础上增加 `reflect` 答案忠实度检查 |

这种设计让前端可以直接切换实验组，也让评测脚本可以复用同一组节点实现批量对比。

---

## 6. 路由设计

`router` 节点结合本地确定性规则和 LLM 路由。高确定性、高风险场景优先由规则处理，避免模型不稳定。

路由类别：

| route | 场景 | 示例 |
| --- | --- | --- |
| `kb` | 政策、流程、材料、时效、安全边界 | “退货需要什么材料？”“风控规则能告诉我吗？” |
| `tool` | 包含完整订单号或工单号，需查实时状态 | “A1100 的快递单号是什么？”“F4002 还差什么资料？” |
| `chitchat` | 闲聊或业务范围外 | “你好”“你们 CEO 是谁？” |
| `handoff` | 用户主动要求人工、投诉、主管介入 | “我要投诉，找你们主管” |

当前支持的业务编号：

| 前缀 | 类型 | 工具 |
| --- | --- | --- |
| `A` | 订单 | `mock_order_lookup` |
| `L` | 物流工单 | `mock_logistics_ticket_lookup` |
| `S` | 售后工单 | `mock_after_sales_ticket_lookup` |
| `F` | 发票工单 | `mock_invoice_ticket_lookup` |
| `C` | 投诉工单 | `mock_complaint_ticket_lookup` |

重要边界：

- `A1007`、`L2003`、`S3022` 这类完整编号会进入工具链。
- “订单A”“物流工单L”“发票工单F”这类不完整编号不会被补全成示例编号，而是由工具返回“缺少完整编号”提示。
- “没有凭证也帮我通过审核”“帮我编一个物流状态”“退款一定今天到账吗”这类安全问题优先进入 `kb`，召回 safety 文档，而不是进入工具链。
- “转人工”“找主管”“投诉升级”直接进入 `handoff`。

---

## 7. 知识库设计

### 7.1 当前知识库

当前正式知识库目录为：

```text
data/knowledge
```

根据当前 loader 实际读取结果：

| doc_type | 数量 | 作用 |
| --- | ---: | --- |
| `policy` | 120 | 对外可用政策依据，覆盖售前、售中、物流、售后 |
| `tool_spec` | 5 | 订单、物流、售后、发票、投诉工具契约 |
| `safety` | 4 | 承诺边界、隐私身份、风控、强制转人工规则 |
| `script` | 4 | 客服话术参考，不作为最高事实依据 |
| `sop` | 4 | 内部流程，如物流异常、售后争议、订单异常、售前咨询 |
| `table` | 4 | 退款周期、物流 SLA、类目退换、工单优先级等结构化规则 |
| `changelog` | 1 | 知识库版本记录 |
| 合计 | 142 | 索引后形成 502 个 chunks |

项目中仍保留 `data/sample_docs` 和 `data/kb`：

- `data/sample_docs`：早期 5 篇示例文档。
- `data/kb`：第一阶段标准客服数据包，120 篇 Markdown。
- `data/knowledge`：当前正式使用的 governed 知识资产目录。

`.env.example` 和当前本地 `.env` 都应将 `DOCS_DIR` 指向：

```text
DOCS_DIR=./data/knowledge
```

### 7.2 元数据治理

核心 Markdown 资产包含 front matter，例如：

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

- 检索过滤。
- rerank 加权。
- 生成上下文排序。
- citation 展示。
- governed retrieval 自动评测。
- 说明“为什么召回这类文档”。

### 7.3 业务结构感知 chunker

`app/ingestion/chunker.py` 不再只是简单按字符切分，而是按客服文档结构组织 chunk：

| chunk_type | 内容 |
| --- | --- |
| `overview` | 适用场景、主题要点 |
| `procedure` | 客服处理原则、标准处理流程 |
| `requirements` | 需要用户提供的信息、可直接答复的情况 |
| `escalation` | 必须转人工或建工单的情况、示例话术、相关工单类型 |
| `reference` | 工具说明、表格、话术、安全规则等参考资产 |

当前主要参数：

```text
MIN_CHUNK_CHARS = 280
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 100
```

这种切分方式可以保留客服业务语义，使“材料要求”“流程步骤”“升级条件”等内容在检索时更容易被定位。

---

## 8. 检索与重排

### 8.1 索引流程

```text
loader.load_docs
  -> chunker.split_documents
  -> embedder.get_embeddings
  -> vectorstore.build_vectorstore
  -> Chroma collection: agentic_rag_kb
```

当前 Embedding 默认使用：

```text
EMBED_MODEL=embedding-3
```

`app/ingestion/vectorstore.py` 将写入 batch 控制为 64，以适配 GLM `embedding-3` 的批量限制。

### 8.2 检索流程

E1/E2/E3 使用完整检索管线：

```text
query
  -> retrieve_with_scores(over_fetch)
  -> supplemental_candidates
  -> rerank
  -> safety frontload
  -> top-k docs
```

默认候选规模：

```text
over_fetch = max(top_k * 8, 32, top_k)
```

E0 则使用 `retrieve_node_plain`，只做纯向量 top-k 检索，不做重排。

### 8.3 doc_type-aware rerank

当前 reranker 是轻量、可解释的 Python 策略，主要包括：

- 去重：避免重复 chunk 占满 top-k。
- 来源多样性惩罚：避免同一来源文档堆叠。
- 业务意图识别：判断 query 是否偏向 safety、SOP、table、tool、requirements 等。
- 知识类型加权：安全问题提高 `safety`，流程问题提高 `sop`，时效/费用问题提高 `table`，实时状态问题提高 `tool_spec`。
- safety 前置：安全敏感问题确保 safety 文档出现在上下文前部。

---

## 9. Mock 业务工具

当前 `data/mock` 下的 mock 数据规模：

| 文件 | 数量 | 工具 |
| --- | ---: | --- |
| `orders.json` | 100 | `mock_order_lookup` |
| `logistics_tickets.json` | 50 | `mock_logistics_ticket_lookup` |
| `after_sales_tickets.json` | 50 | `mock_after_sales_ticket_lookup` |
| `invoice_tickets.json` | 20 | `mock_invoice_ticket_lookup` |
| `complaint_tickets.json` | 20 | `mock_complaint_ticket_lookup` |

这些工具用于模拟真实客服系统中的订单查询、物流工单查询、售后工单查询、发票工单查询和投诉工单查询。它们不是 LangChain `BaseTool`，而是由 LangGraph 的 `router -> tool` 显式边触发，这样前端和评测脚本可以清楚观察工具调用发生在何处。

工具层还负责处理不完整编号：

```text
输入：发票工单F能加急吗
输出：编号不完整，请提供完整订单号或工单号，例如 A1007、L2003、S3008。
```

---

## 10. 答案生成与安全约束

`generate` 节点根据 route 使用不同 prompt：

- `chitchat`：自然客服口吻，不强制依赖知识库。
- `kb` / `tool`：严格基于知识库资料和工具结果回答。

生成约束包括：

- 不编造知识库未提供的信息。
- 不编造订单、物流、售后、发票、投诉工单状态。
- 不承诺退款一定通过、赔付一定成功、库存一定存在、物流一定按时送达。
- 涉及风控、隐私、质检争议、高价值订单、投诉升级时，回答应保守并建议人工核实。

`reflect` 节点会判断答案是否忠实于提供资料。若答案不忠实，且仍有重试次数，则可回到 `rewrite_query` 重新检索；否则结束，避免无限循环。

---

## 11. 前端与 SSE

前端位于：

```text
app/ui/index.html
```

页面包含：

- 左侧聊天区：展示用户问题、AI 回答、引用和工具结果。
- 右侧时间线：展示 router、retrieve、grade、rewrite、tool、generate、reflect、handoff 等步骤。
- 顶部实验组切换：E0、E1、E2、E3。
- 快捷演示问题。
- 重建索引按钮。

后端 `/api/chat` 输出四类 SSE 事件：

| 事件 | 含义 |
| --- | --- |
| `step` | 某个 Agent 节点结束，返回节点输入输出摘要 |
| `token` | `generate` 节点的流式 token |
| `done` | 完成整轮对话，返回最终答案、引用和结束原因 |
| `error` | 执行异常 |

这种设计让系统不仅能回答问题，还能展示“为什么这样回答”。

---

## 12. 配置与运行

### 12.1 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

在当前本地环境中，裸 `python` 可能不可用，建议优先使用：

```bash
.venv/bin/python
```

如果 `.venv/bin/pip` 因项目路径变更失效，可使用：

```bash
.venv/bin/python -m pip
```

### 12.2 配置 `.env`

```bash
cp .env.example .env
```

关键配置：

```text
OPENAI_API_KEY=你的模型服务密钥
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
LLM_MODEL=glm-4-flash
EMBED_MODEL=embedding-3
TOP_K=4
MAX_RETRIES=3
CHROMA_DIR=./.chroma
DOCS_DIR=./data/knowledge
HOST=0.0.0.0
PORT=8000
```

### 12.3 构建索引

```bash
.venv/bin/python -m scripts.ingest
```

默认会清空并重建 `.chroma/`，避免重复追加 chunk。当前本地 Chroma 中已有：

```text
collection: agentic_rag_kb
embeddings: 502
```

### 12.4 启动服务

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问：

```text
http://localhost:8000
```

---

## 13. 推荐演示问题

| 场景 | 问题 | 展示重点 |
| --- | --- | --- |
| 工具调用 | `我的订单 A1007 现在是什么状态？` | E0 只能泛化回答，E1+ 调用订单工具 |
| 物流工单 | `物流工单 L2003 处理到哪一步了？` | E1+ 调用物流工单工具 |
| 售后工单 | `帮我看 S3022 质检到哪了` | E1+ 调用售后工单工具 |
| 发票工单 | `发票工单 F4002 还差什么资料？` | E1+ 调用发票工具 |
| 投诉工单 | `C5005 服务态度投诉受理了吗？` | E1+ 调用投诉工单工具 |
| 缺少编号 | `我需要看订单A` | 不把 A 补全成 A1001 |
| 投诉升级 | `我要投诉，找你们主管` | 直接 handoff |
| 安全边界 | `退款一定能今天到账吗？你能保证吗？` | safety 前置，拒绝承诺 |
| SOP 流程 | `售后质检争议处理流程是什么？` | 召回 SOP + policy |
| 材料凭证 | `退货需要提供什么材料？` | requirements chunk 靠前 |
| 结构化表 | `信用卡退款周期是多久？` | table 优先于普通 policy |
| 风控边界 | `风控拦截的具体规则能告诉我吗？` | 不泄露内部命中规则 |

演示时可以先用 E3 展示完整时间线，再切换 E0 对比工具类问题。

---

## 14. 评测体系

当前项目包含多套评测集：

| 文件 | 数量 | 用途 |
| --- | ---: | --- |
| `eval/testset.jsonl` | 32 | 早期端到端消融评测集 |
| `eval/testset_governed.jsonl` | 30 | governed retrieval 评测 |
| `eval/testset_agentic_showcase.jsonl` | 80 | agentic showcase 问题池 |
| `eval/testset_large.jsonl` | 254 | 第一阶段大评测集 |

### 14.1 Governed Retrieval Eval

运行：

```bash
.venv/bin/python -m eval.run_governed_retrieval_eval
```

当前快照：

| metric | value |
| --- | ---: |
| n | 30 |
| pass_rate | 1.000 |
| doc_type_hit | 1.000 |
| category_hit | 1.000 |
| chunk_type_hit | 1.000 |
| title_hit | 1.000 |
| top_doc_type_hit | 1.000 |
| tool_id_hit | 1.000 |
| tool_name_hit | 1.000 |

该评测不调用 LLM，主要验证检索层是否遵守知识治理预期。

### 14.2 Agentic Showcase Eval

运行示例：

```bash
.venv/bin/python -m eval.run_agentic_showcase_eval --sample-per-category 1 --timeout-s 60
```

当前 `eval/results/agentic_showcase.md` 快照：

| metric | value |
| --- | ---: |
| n_cases | 11 |
| n_distinguishing_cases | 11 |
| n_errors | 0 |
| distinguishing_rate | 1.000 |
| error_rate | 0.000 |
| avg_distinct_signatures | 3.273 |

该评测用于展示 E0/E1/E2/E3 在工具调用、缺少编号、转人工、安全边界、SOP、材料和表格类问题上的行为差异。

### 14.3 Gradient Eval

当前 `eval/results/agentic_gradient.md` 快照：

| stage | action | governed context | evidence grade | reflection | no error | score | avg latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E0 Retrieval | 36.4% | 25.0% | 0.0% | 0.0% | 100.0% | 25.3 | 8055 ms |
| E1 Routed/Tools | 100.0% | 62.5% | 0.0% | 0.0% | 100.0% | 50.6 | 6746 ms |
| E2 Graded | 100.0% | 62.5% | 100.0% | 0.0% | 100.0% | 70.6 | 7619 ms |
| E3 Full Agentic | 100.0% | 62.5% | 100.0% | 90.9% | 100.0% | 88.8 | 7674 ms |

该评测更适合展示“能力阶梯”：E1 体现行动正确性，E2 体现证据打分，E3 体现反思检查。

### 14.4 早期 E0/E1/E2/E3 消融评测

`eval/results/comparison.md` 保留了一次 32 题端到端消融快照：

| 实验组 | n | 路由准确率 | 工具 F1 | Hit@3 | Hit@5 | MRR | Faithfulness | AnswerRelev. | ContextPrec. | 延迟 p50(ms) | 延迟 p95(ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E0 Naive RAG | 32 | 0.562 | 0.000 | 0.833 | 0.889 | 0.782 | 0 | 0 | 0 | 5390.821 | 9954.585 |
| E1 + 路由 + 工具 | 32 | 0.969 | 1.000 | 0.944 | 0.944 | 0.815 | 0 | 0 | 0 | 5983.727 | 10970.968 |
| E2 + 查询改写 | 32 | 0.969 | 1.000 | 0.944 | 1.000 | 0.838 | 0 | 0 | 0 | 11859.154 | 27751.020 |
| E3 Full Agentic | 32 | 0.969 | 1.000 | 0.889 | 1.000 | 0.796 | 0.544 | 0.453 | 0.562 | 12361.206 | 27254.739 |

这组结果仍可作为历史对照，但当前更推荐结合 governed retrieval 和 gradient eval 展示最新知识库治理能力。

---

## 15. 结果解读

当前结果体现出几个关键结论：

1. **路由和工具调用显著提升实时查询能力。**
   E0 遇到订单或工单问题只能检索静态知识库，E1+ 能直接调用对应 mock 工具。

2. **受治理检索能解释“为什么召回这些资料”。**
   safety、SOP、table、requirements 等 doc_type 参与检索排序，使系统不只是相似度匹配，而是按客服业务语义组织证据。

3. **E2 的 grade/rewrite 提供检索修正能力。**
   当初始检索资料不足时，系统可以改写查询再次检索，适合复杂或口语化问题。

4. **E3 的 reflect 增加了答案自检环节。**
   反思节点不能完全消除模型不确定性，但能把“答案是否忠实于资料”变成显式步骤。

5. **Agentic RAG 有额外延迟成本。**
   完整流程包含更多 LLM 调用，真实落地时需要在响应速度、准确性和可信度之间取舍。

---

## 16. 项目亮点

### 16.1 显式 Agent 状态图

项目没有使用不可控的黑盒 Agent，而是用 LangGraph 将 router、retrieve、grade、rewrite、tool、generate、reflect、handoff 拆成可观察节点，适合客服这种需要稳定流程的场景。

### 16.2 工具调用边界清晰

系统区分静态政策问答和实时状态查询。订单、物流、售后、发票、投诉等具体状态通过工具返回，避免知识库编造实时结果。

### 16.3 知识库治理能力强

知识资产带有 `doc_type`、`category`、`business_stage`、`visibility`、`priority` 等元数据，检索和生成都能使用这些信息。

### 16.4 安全边界前置

退款承诺、赔付承诺、风控细节、隐私信息、无凭证审核等问题会优先召回 safety 文档，避免被普通 policy 误导。

### 16.5 演示与评测闭环

前端能实时展示 Agent 时间线；评测脚本能记录 route、steps、tool、top knowledge、latency 等信号，方便课堂展示和实验分析。

---

## 17. 局限性

### 17.1 mock 工具不等于真实业务系统

当前工具读取本地 JSON，不包含真实系统的鉴权、权限、日志审计、失败重试和数据脱敏。

### 17.2 rerank 仍是启发式策略

当前 reranker 可解释、轻量，但不是 cross-encoder。复杂语义排序仍可能不如专门的重排模型。

### 17.3 模型判断仍有随机性

router、grade、rewrite、reflect 都依赖 LLM 的一部分判断。项目通过规则兜底和防御性解析降低风险，但不能完全消除模型不稳定。

### 17.4 评测规模仍偏课程项目

虽然当前已有 30 条 governed retrieval、80 条 showcase、254 条大测试集，但还不足以代表真实生产客服的长尾输入、恶意诱导、多轮上下文和高并发场景。

### 17.5 延迟随 Agent 能力增加

E2/E3 因为增加打分、改写和反思，延迟通常高于 E0/E1。生产系统需要设置更细的超时、缓存和降级策略。

---

## 18. 未来工作

### 18.1 接入真实业务接口

- 订单查询。
- 物流轨迹查询。
- 售后工单状态查询与创建。
- 发票申请状态查询。
- 投诉工单查询与升级。
- 用户身份核验和权限校验。

### 18.2 引入更强检索方案

- BM25 + 向量混合检索。
- Cross-Encoder reranker。
- 多查询扩展。
- 按业务主题分索引。
- 查询意图驱动 metadata filter。

### 18.3 支持多轮对话记忆

当前系统主要面向单轮问题。未来可以加入会话记忆，使系统理解“刚才那个订单”“我说的是售后单”等上下文引用。

### 18.4 强化安全与合规

- 敏感信息脱敏。
- 高风险回答人工确认。
- API 权限控制。
- 审计日志。
- 质检和风控规则的更细粒度拒答策略。

### 18.5 扩大评测体系

- 更多真实用户问法。
- 更多安全攻击和诱导场景。
- 多轮对话评测。
- 不同模型横向对比。
- 人工客服满意度评估。

---

## 19. 项目结论

本项目实现了一个较完整的 Agentic RAG 电商客服原型。相比朴素 RAG，它不仅能检索和生成，还能判断问题类型、调用业务工具、治理检索上下文、改写查询、检查答案忠实度，并在高风险或资料不足时转人工。

当前版本已从早期 5 篇示例文档升级为 `data/knowledge` governed 知识库，实际读取 142 个知识资产、索引 502 个 chunks；工具能力也从单一订单查询扩展到订单、物流、售后、发票、投诉 5 类 mock 工具。评测体系同时覆盖检索治理、行为差异和能力梯度，能够较清楚地展示 Agentic RAG 在客服场景中的价值。

总体而言，本项目适合作为课程项目、技术演示和客服智能化原型，也为后续接入真实业务接口、增强检索模型、扩展多轮对话和完善安全合规提供了清晰基础。
