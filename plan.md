# yd-Agent 企业级 AI 助手 — 全阶段实施计划

## 项目概述

面向私有化部署即时通讯（IM）软件的企业级 AI 助手系统。用户通过 @机器人 形式提问，机器人可调用 IM API 完成操作。

## 技术栈

| 类别 | 技术选型 |
|------|----------|
| 语言 | Python 3.12+ |
| AI 编排 | LangGraph (状态机 + 多智能体) |
| LLM | qwen3.6-flash（阿里百炼 DashScope） |
| 嵌入模型 | text-embedding-v4 |
| 重排序模型 | qwen3-vl-rerank |
| 向量数据库 | FAISS（二期）/ Chroma（后续） |
| 图数据库 | NetworkX（二期）/ SQLite 邻接表 + 递归 CTE（后续） |
| 关系/缓存 | Redis (会话记忆 + 缓存) |
| Web 框架 | FastAPI |
| 容器化 | Docker + Docker Compose |
| 评估框架 | RAGAS + 自定义 LLM Judge |
| 测试 | pytest |

## 架构总览

```
                ┌─────────────┐
                │  Supervisor │  ← 分析用户意图，决定调度哪些 Worker
                └──────┬──────┘
         ┌───────┬─────┴─────┬───────┐
         ▼       ▼           ▼       ▼
    ┌────────┐┌────────┐┌────────┐┌────────┐
    │ 检索   ││ 代码   ││ 动作   ││ 总结   │
    │ Worker ││ Worker ││ Worker ││ Worker │
    └────────┘└────────┘└────────┘└────────┘
         │          │         │         │
         └──────────┴────┬────┴─────────┘
                         ▼
               ┌─────────────────┐
               │  Refiner (反思) │  ← 自我批评，最多重试 2 次
               └─────────────────┘
```

---

## 一期：多智能体编排 ✅ 已完成

### 目标
基于 LangGraph 构建 Supervisor + 4 Worker + Refiner 多智能体架构，实现并行调度与自我纠错。

### 已交付
- FastAPI 应用入口 + lifespan 启动图实例
- Settings 配置类（LLM、服务、沙箱参数）
- ChatRequest / ChatResponse Pydantic 模型
- GET /health 健康检查
- POST /chat 对话（非流式）
- POST /chat/stream 对话（SSE 流式）
- LangGraph AgentState + WorkerResult 状态定义
- 6 套 Prompt 模板（Supervisor + 4 Worker + Refiner）
- LLM 工厂：基于 `langchain.chat_models.init_chat_model`
- Supervisor 节点：意图分析 + 路由分发
- Retrieval Worker：知识检索（一期 LLM 占位）
- Code Worker：LLM 生成代码 + Docker 沙箱执行
- Action Worker：LLM 生成 REST 规格 + httpx 调用
- Summary Worker：聚合多 Worker 结果生成最终回答
- Refiner 节点：LLM 评分 0-10，低于 7 触发重试（最多 2 次）
- StateGraph 构建：Send API 并行分发 + 条件路由
- Docker 沙箱：在 python:3.12-slim 容器中执行代码
- pytest 测试套件（5 个测试，含 mock LLM/mock Docker/mock httpx）

---

## 二期：GraphRAG 增强推理 🔜 当前阶段

### 目标
升级 retrieval_worker 从 LLM 占位到真正的 GraphRAG 检索系统，支持跨文档多跳推理。

### 待实施

**新增文件（16 个）**

```
app/agent/storage/
├── __init__.py                    # 存储模块入口
├── vector_store.py                # FAISSStore：FAISS IndexFlatIP 向量存储
├── graph_store.py                 # GraphStore：NetworkX DiGraph 图存储
└── kv_store.py                    # JsonKVStore：JSON 文件 KV 存储

app/agent/ingestion/
├── __init__.py                    # 摄入模块入口
├── chunker.py                     # 文档分块器（固定大小 + 重叠）
├── extractor.py                   # LLM 实体/关系抽取 + gleaning
└── ingestion_graph.py             # 摄入 StateGraph 构建

app/agent/retrieval/
├── __init__.py                    # 检索模块入口
├── keywords.py                    # 关键词提取节点
├── search.py                      # local/global/naive 搜索节点
├── context_builder.py             # 上下文构建 + weighted polling
└── chunk_picker.py                # 加权轮询 chunk 选择器

app/agent/storage_manager.py       # 存储上下文管理器（初始化/持久化/获取）

app/api/routes/documents.py        # 文档管理 API 端点

test/api/
├── test_documents.py              # 文档 API 测试
└── test_graphrag.py               # GraphRAG 检索测试
```

**修改文件（12 个）**

| 文件 | 变更内容 |
|------|----------|
| `requirements.txt` | 添加 `faiss-cpu>=1.8.0`、`networkx>=3.3` |
| `app/config/settings.py` | 添加 `embedding_model`、`storage_dir` 等 |
| `app/agent/constants.py` | 添加 `GRAPH_FIELD_SEP`、`DEFAULT_ENTITY_TYPES`、chunk 参数 |
| `app/agent/exceptions.py` | 添加 `IngestionError`、`StorageError` |
| `app/agent/llm/factory.py` | 添加 `create_embeddings()` |
| `app/agent/prompts.py` | 新增摄入/检索 Prompt，更新 `RETRIEVAL_WORKER_PROMPT` |
| `app/agent/state.py` | 新增 `IngestionState` TypedDict |
| `app/agent/nodes/retrieval_worker.py` | 重写：VDB→GraphRAG 检索→上下文构建→输出 |
| `app/main.py` | lifespan 中初始化 storage_manager，注册 documents 路由 |
| `app/domain/schemas.py` | 添加文档相关请求/响应模型 |
| `api-doc.md` | 添加 `/documents/*` 端点文档 |
| `dir-structure.md` | 更新目录结构 |

### 新增 API

| 端点 | 说明 |
|------|------|
| POST /documents/ingest | 文档摄入（分块→抽取→嵌入→存储） |
| GET /documents/stats | 文档统计（总数、chunk 数、实体数、关系数） |
| GET /documents | 列出所有文档 |
| DELETE /documents/{doc_id} | 删除文档及关联数据 |

### 检索流程

```
Supervisor 调度 retrieval_worker
    │
    ▼
┌──────────────┐
│ 关键词提取    │  LLM: 提取 ll_keywords + hl_keywords
└──────┬───────┘
       │
  ┌────┴────────────────────┐
  ▼              ▼                    ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│ local  │  │ global   │  │  naive   │  并行搜索
│ search │  │ search   │  │  search  │
│实体VDB │  │关系VDB   │  │ 分块VDB  │
└───┬────┘  └────┬─────┘  └────┬─────┘
   │            │              │
   └────────────┴──────┬───────┘
                       ▼
                ┌──────────────┐
                │ 上下文构建    │  weighted polling
                └──────┬───────┘
                       ▼
            返回 worker_results → summary_worker

回退：如果 entities_vdb 为空（无文档），直接用 LLM 回答
```

---

## 三期：长期记忆与用户画像 📋 计划中

### 目标
实现跨会话的用户记忆与偏好学习，支持个性化交互和历史复用。

### 核心能力

**分级记忆管理（MemGPT 风格）**

| 记忆类型 | 生命周期 | 存储内容 |
|----------|----------|----------|
| 核心记忆 | 永久 | 用户角色、偏好、常见决策模式、报告模板 |
| 工作记忆 | 24小时滑动窗口 | 近期对话上下文、当前任务状态 |

**用户画像系统**
- 每个用户长期保存：历史提问偏好、常见决策、之前自动生成的报告模板
- 用户画像 embedding 向量化，支持相似用户推荐

**跨会话复用**
- 示例：第二次问"帮我写周报"，自动根据上次的格式 + 本次知识库更新内容生成
- 模板学习：从历史交互中提取可复用的回答结构

### 技术组件（规划）
- Redis 会话记忆缓存
- 用户画像向量存储（FAISS/Chroma）
- 记忆提取 Worker（从对话中提取关键信息）
- 记忆检索 Worker（查询相关历史记忆）
- AgentState 扩展：`session_id`、`user_profile`、`core_memory`、`working_memory`

### 待定设计决策
- 记忆提取时机：实时 vs 会话结束后异步
- 记忆衰减策略：时间加权 vs 重要性加权
- 隐私与遗忘机制：用户主动删除记忆的接口

---

## 四期：自我评估与主动学习闭环 📋 计划中

### 目标
建立系统化的回答质量评估与持续改进机制，让模型越用越聪明。

### 核心能力

**LLM-as-Judge 异步评估**
- 每次回答后，后台异步评估忠实度、相关性、完整性
- 集成 RAGAS 自动评估框架
- 接入 LangSmith 对话追踪

**难例挖掘与积累**
- 低于质量阈值时自动记录到"未命中案例库"
- 后台任务：用更强模型生成正确答案
- 纳入长期记忆供后续参考

**人工反馈闭环**
- 提供 👍/👎 反馈接口
- 反馈数据用于微调重排序模型权重（qwen3-vl-rerank）
- 增量训练：周期性用积累的反馈数据更新模型

### 技术组件（规划）
- RAGAS 评估 pipeline
- 难例存储与检索（SQLite / FAISS）
- 后台异步任务队列（Redis + 后台线程）
- 重排序模型微调 pipeline
- 反馈 API：POST /feedback（👍/👎 + 可选文字反馈）
- 评估仪表板：GET /eval/stats

### 与一期 Refiner 的关系
一期 Refiner 是同步的、请求内的反思纠错（评分 + 重试，最多 2 次）。四期在此基础上做系统化的异步评估 + 难例积累 + 模型持续改进，是更高维度的质量保障体系。两者互补：
- Refiner：实时拦截低质量回答，立即重试修正
- 四期：长期追踪质量趋势，从数据层面提升系统能力

---

## 四阶段关系

```
一期：多智能体编排 ──→ 二期：GraphRAG 增强推理
        │                      │
        │   基础编排能力        │   知识检索能力
        │                      │
        └────────┬─────────────┘
                 ▼
        三期：长期记忆与用户画像
                 │
                 │   个性化 + 上下文连续性
                 ▼
        四期：自我评估与主动学习
                 │
                 │   质量保障 + 持续改进
                 ▼
           完整的 yd-Agent
```
