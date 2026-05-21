# Agentic RAG · 客服 AI Demo

一个体现 **Agentic RAG** 的电商客服聊天 AI：用 LangGraph 把「路由 / 多轮检索 / 查询改写 / 工具调用 / 自我反思 / 转人工」编排为状态图，右侧 UI 实时展示每一步决策。

**默认大模型：智谱 GLM**（`glm-4-flash` + `embedding-3`，走 OpenAI 兼容协议）。附带 **32 条**人工标注测试集与 **4 组消融实验**脚本，可直接复现并写入课程报告。

---

## 1. 架构

```
┌──── 用户 ────┐
       ▼
   router ──┬──► handoff ─────────────────────────────► END（转人工话术）
            ├──► tool ────────┐
            ├──► chitchat ────┼──► generate ──► reflect? ──► END
            └──► retrieve ──► grade ──► rewrite ──► retrieve …
                     │              │
                     └──── generate ◄┘
                              │
                    (grade 全否 & 重试用尽)
                              ▼
                          handoff ──► END
```

### 1.1 路由（四选一）

| route | 触发场景 | 后续节点 |
| --- | --- | --- |
| `kb` | 退换货、配送、发票、会员、故障判定等业务问题 | retrieve → grade → … → generate |
| `tool` | 含订单号（如 A1001）的物流/订单查询 | tool_call → generate |
| `chitchat` | 闲聊、业务范围外问题（如问 CEO、天气） | generate（自然口吻，不强制引用资料） |
| `handoff` | 主动要求转人工 / 投诉升级 | handoff（400 电话 + 3 分钟响应承诺） |

### 1.2 Agent 节点

| 节点 | 作用 |
| --- | --- |
| **router** | 意图分类（kb / tool / chitchat / handoff） |
| **retrieve** | 向量召回；E1+ 经 `pipeline.retrieve_and_rerank`（去重 + 来源多样性），E0 为纯 cosine top-k |
| **grade_docs** | 对每个片段做 yes/no 相关性判断（Self-RAG 风格） |
| **rewrite_query** | LLM 改写查询，进入下一轮检索 |
| **tool_call** | 调用 `mock_order_lookup`（示例订单 A1001–A1004） |
| **generate** | 基于资料 / 工具结果生成回答（SSE 流式） |
| **reflect** | 判断答案是否忠于资料；不通过可回到 rewrite |
| **human_handoff** | 用户主动转人工，或检索/打分多轮失败后兜底 |

### 1.3 RAG 索引与检索（显式分层）

**索引（`app/ingestion/`）**

```
loader → chunker → embedder → vectorstore
  │         │          │            │
  读 md    两段切块   embedding-3   Chroma 持久化
```

- **chunker**：Markdown 标题切分 + 递归字符切分（默认 400 字 / 60 重叠）
- **embedder**：智谱 `embedding-3`（2048 维），工厂在 `embedder.py`

**检索（`app/retrieval/`）**

```
query → retriever (Chroma similarity) → reranker → top-k
```

- **reranker**：去重 + 同来源惩罚（可替换为 cross-encoder，见 FAQ）
- **query_rewriter**：agent 内 rewrite 节点调用，与检索层解耦

---

## 2. 目录

```
agentic-rag/
├── README.md
├── requirements.txt
├── .env.example
├── data/sample_docs/          5 份示例客服 markdown
├── app/
│   ├── main.py                FastAPI 入口（启动时校验 API Key）
│   ├── config.py              配置（读 .env，get_settings 不缓存）
│   ├── ingestion/
│   │   ├── loader.py          ① 加载 .md / .txt
│   │   ├── chunker.py         ② 切块
│   │   ├── embedder.py        ③ Embedding 工厂（默认 GLM embedding-3）
│   │   ├── vectorstore.py     ④ Chroma 读写
│   │   └── indexer.py         build_index() 编排
│   ├── retrieval/
│   │   ├── retriever.py       similarity_search_with_score
│   │   ├── reranker.py        去重 + 多样性重排
│   │   ├── query_rewriter.py  查询改写 prompt + LLM
│   │   └── pipeline.py        retrieve_and_rerank()
│   ├── agent/
│   │   ├── graph.py           LangGraph 编译 + 4 组 AgentConfig
│   │   ├── nodes.py           各节点实现
│   │   ├── state.py           GraphState / Route 类型
│   │   ├── prompts.py         各节点 system prompt
│   │   └── tools.py           mock_order_lookup + 转人工话术
│   ├── api/chat.py            SSE 流式 /api/chat
│   └── ui/index.html          单页对话 + Agent 时间线
├── scripts/ingest.py          构建索引（默认 wipe & rebuild）
└── eval/
    ├── testset.jsonl          32 条标注（含 handoff / refuse / chitchat）
    ├── metrics.py             路由 / Hit@k / MRR / 延迟
    ├── ragas_eval.py          RAGAS 生成质量（可选）
    ├── run_eval.py            跑 4 组消融
    ├── compare.py             生成 comparison.md / case_study.md
    └── results/               实验输出（gitignore *.json）
```

---

## 3. 快速开始

### 3.1 环境

需要 **Python 3.10+**（已在 3.14 上验证）。

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3.2 配置 `.env`

```bash
cp .env.example .env
# 填入智谱 API Key（变量名仍为 OPENAI_API_KEY，兼容 langchain_openai）
```

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | （必填） | 智谱控制台 Key |
| `OPENAI_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4/` | 可换 OpenAI / DeepSeek 等兼容端点 |
| `LLM_MODEL` | `glm-4-flash` | 对话模型 |
| `EMBED_MODEL` | `embedding-3` | 嵌入模型（2048 维） |
| `TOP_K` | `4` | 检索条数 |
| `MAX_RETRIES` | `3` | grade 失败后的最大改写轮次（demo 可改为 `1` 加快兜底转人工） |

换回 OpenAI / DeepSeek：只改上述 4 个 API 相关变量，代码无需改动。

### 3.3 构建知识库

```bash
python -m scripts.ingest
```

默认 **清空后重建**（`rebuild=True`），避免 Chroma `from_documents` 追加导致 chunk 翻倍。  
若确需追加（高级）：`python -m scripts.ingest --no-rebuild`。

### 3.4 启动

```bash
# 建议在项目根目录、已 activate .venv 后：
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 [http://localhost:8000](http://localhost:8000)。  
顶栏可切换 **E0 / E1 / E2 / E3** 四种 agent 配置；**清空对话** 后再换变体对比更公平。

---

## 4. 演示脚本

观察**右侧 Agent 思考过程**：

| # | 问题 | 预期路径 | 看点 |
| --- | --- | --- | --- |
| 1 | 你们的退货政策是什么？ | kb → retrieve → grade → generate → reflect | 单跳 + 引用 |
| 2 | 我的订单 A1001 现在到哪了？ | tool → tool_call → generate | 不调 KB，走订单 mock |
| 3 | 我买的耳机突然没声音了，能退吗？ | kb → retrieve → grade → rewrite → retrieve → … | 多轮改写补检索 |
| 4 | 我要转人工 | handoff | 直接转人工话术 + 右栏 `human_handoff` 步骤 |

同一问题在 **E0 vs E3** 下对比：E0 无 router（订单题也会硬检索）、无 grade/rewrite/reflect；E3 步骤最多、延迟最高。

---

## 5. 实验复现

### 5.1 四组消融

| 实验组 | router | rerank | grade | rewrite | reflect | tools |
| --- | :-: | :-: | :-: | :-: | :-: | :-: |
| **E0 Naive RAG** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| **E1 +路由+工具** | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ |
| **E2 +查询改写** | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **E3 Full Agentic** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

- **E0**：`retrieve_node_plain`，仅 cosine top-k，无 rerank —— 作为真·朴素基线。  
- **E1+**：`retrieve_and_rerank`，每档相对上一档为**单一增量**

### 5.2 测试集（`eval/testset.jsonl`）

共 **32 条**，类别包括：

| category | 条数 | 说明 |
| --- | --- | --- |
| single-hop | 10 | 单文档问答 |
| multi-hop | 8 | 需多文档综合 |
| tool | 6 | 订单查询 |
| refuse | 4 | 业务范围外 → 期望 `chitchat` |
| chitchat | 2 | 寒暄 |
| handoff | 2 | 主动转人工 |

### 5.3 跑实验

```bash
# 推荐：先跑路由/检索/延迟（约 15–25 分钟，32 条 × 4 组）
python -m eval.run_eval --all --no-ragas

# 生成对比表 + 案例分析
python -m eval.compare

# 可选：仅对已有 full.json 补 RAGAS（约 6–7 分钟，不重跑 graph）
python -c "
import json
from pathlib import Path
from eval.ragas_eval import run_ragas
p = Path('eval/results/full.json')
d = json.loads(p.read_text(encoding='utf-8'))
d['metrics']['ragas'] = run_ragas(d['records'])
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
print(d['metrics']['ragas'])
"
python -m eval.compare

# 或一次性跑满（含 RAGAS，耗时会显著增加）
python -m eval.run_eval --all
```

产物：

- `eval/results/<variant>.json` — 每条 query 的完整 record  
- `eval/results/comparison.md` / `.csv` — 四组指标表  
- `eval/results/case_study.md` — E0 错 / E3 对的典型案例  

### 5.4 指标说明

| 指标 | 含义 | 越好 |
| --- | --- | --- |
| 路由准确率 | `actual_route` 是否等于 `expected_route`（含 handoff） | ↑ |
| 工具 F1 | 该调工具时是否真调了 `tool_call` | ↑ |
| Hit@3 / Hit@5 | 至少一个标准来源出现在 Top-K（per-query 0/1） | ↑ |
| MRR | 标准来源的平均倒数排名 | ↑ |
| Faithfulness (RAGAS) | 答案是否忠于检索上下文 | ↑ |
| Answer Relevancy | 答案是否切题 | ↑ |
| Context Precision | 检索上下文是否相关 | ↑ |
| 延迟 p50 / p95 | 端到端耗时（ms） | ↓ |

> RAGAS 会跳过 `chitchat` / `refuse` / `handoff`（无稳定 reference/context）。使用 GLM 时可能出现 “LLM returned 1 generations instead of requested 3”，绝对值偏低属已知限制，宜作**同评估器下的相对比较**或仅报告 E3 一档。

### 5.5 参考结果（本机一次 `--no-ragas` + E3 RAGAS）

以下为仓库内一次完整跑通的快照，**换模型/API 后数值会变化**，以你本地 `comparison.md` 为准：

| 实验组 | 路由准确率 | 工具 F1 | Hit@3 | Hit@5 | MRR | Faithfulness | p50 延迟 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E0 Naive | 0.562 | 0.000 | 0.833 | 0.889 | 0.782 | — | ~5.4s |
| E1 +路由+工具 | 0.969 | 1.000 | 0.944 | 0.944 | 0.815 | — | ~6.0s |
| E2 +改写 | 0.969 | 1.000 | 0.944 | 1.000 | 0.838 | — | ~11.9s |
| E3 Full | 0.969 | 1.000 | 0.889 | 1.000 | 0.796 | 0.544 | ~12.4s |

---

## 6. 常见问题

**API / 配置**

- **`OPENAI_API_KEY` 未设置**：启动即报错（`main.py` fail-fast）；检查 `.env`。  
- **改 `.env` 后行为没变**：`get_graph()` 有编译缓存；开发时可 `from app.agent.graph import clear_graph_cache; clear_graph_cache()` 后重试。`get_settings()` 每次新建，**无需**为改 Key 清缓存。  
- **GLM 结构化输出**：router/grade/reflect 使用手写 JSON/yes-no 解析（`nodes.py`），未依赖 `with_structured_output`。

**索引 / 检索**

- **重复 ingest 导致检索变差**：勿多次无 `--rebuild` 追加；默认 `scripts.ingest` 已 wipe。  
- **换嵌入模型**：改 `EMBED_MODEL` 后必须 `python -m scripts.ingest` 全量重建。  
- **换本地中文嵌入**：改 `app/ingestion/embedder.py` 为 `HuggingFaceEmbeddings`，并 `pip install sentence-transformers`。  
- **换 reranker**：只改 `app/retrieval/reranker.py` 的 `rerank()`。  
- **改切块**：改 `app/ingestion/chunker.py` 的 `DEFAULT_CHUNK_SIZE` 等。

**UI / 演示**

- **页面无响应、右侧无步骤**：硬刷新（Cmd+Shift+R）或无痕窗口；确认 `uvicorn` 在 `.venv` 内启动。  
- **业务范围外问题很僵**：应走 `chitchat` 或主动 `handoff`；若仍长时间思考，将 `.env` 中 `MAX_RETRIES=1` 加快失败兜底。  
- **演示时 agent 太慢**：顶栏用 E1/E2 或 `MAX_RETRIES=1`；评测完整 agent 再用 E3 + `MAX_RETRIES=3`。

**观测**

- **LangSmith**：在 `.env` 开启 `LANGCHAIN_TRACING_V2` 等变量，见 [smith.langchain.com](https://smith.langchain.com)。

---

## 7. 许可

仅用于课程学习与演示。
