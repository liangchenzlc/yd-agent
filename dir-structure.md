# yd-Agent 目录结构

## 项目概述
基于 LangGraph 的企业级 AI 多智能体助手系统，支持 GraphRAG 增强检索。

## 目录树

```
yd-Agent/
├── .env.example                        # 环境变量模板（LLM 配置、服务端口等）
├── .gitignore                          # Git 忽略规则（__pycache__、.env、venv 等）
├── api-doc.md                          # API 接口文档（含 GraphRAG 文档管理 API）
├── dir-structure.md                    # 目录结构说明（本文件）
├── plan.md                             # 四期工程整体规划
├── plan2.md                            # 二期 GraphRAG 详细实施计划
├── pytest.ini                          # pytest 配置
├── requirements.txt                    # Python 依赖清单（新增 faiss-cpu、networkx）
├── app/                                # 应用主目录
│   ├── __init__.py
│   ├── main.py                         # FastAPI 入口，lifespan 初始化 StorageManager
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                 # Pydantic Settings（新增 embedding、storage 配置）
│   ├── domain/
│   │   ├── __init__.py
│   │   └── schemas.py                  # 请求/响应模型（新增 Document 相关模型）
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py               # GET /health 健康检查
│   │       ├── chat.py                 # POST /chat, POST /chat/stream
│   │       ├── documents.py            # 新增：文档管理 API（摄入/统计/列出/删除）
│   │       ├── memory.py               # 新增：记忆管理 API（查看/删除记忆和画像）
│   │       └── eval.py                  # 四期新增：评估与反馈 API（摘要/难例/反馈 10 个端点）
│   └── agent/
│       ├── __init__.py
│       ├── _version.py                 # 版本号
│       ├── constants.py                # 常量（新增 GraphRAG、分块、检索参数）
│       ├── exceptions.py               # 异常类（新增 StorageError、IngestionError）
│       ├── state.py                    # LangGraph 状态（新增 IngestionState）
│       ├── prompts.py                  # Prompt 模板（RETRIEVAL_WORKER_PROMPT 升级）
│       ├── graph.py                    # StateGraph 构建（接收 storage_manager 参数）
│       ├── storage_manager.py          # 新增：存储上下文管理器
│       ├── storage/                    # 新增：存储层
│       │   ├── __init__.py
│       │   ├── vector_store.py         # FAISSStore：FAISS 向量存储（IndexFlatIP）
│       │   ├── graph_store.py          # GraphStore：NetworkX DiGraph 图存储
│       │   └── kv_store.py            # JsonKVStore：JSON 文件 KV 存储
│       ├── ingestion/                  # 新增：文档摄入管道
│       │   ├── __init__.py
│       │   ├── chunker.py             # 文本分块器（段落优先 + 固定窗口回退）
│       │   ├── extractor.py           # LLM 实体/关系抽取 + gleaning
│       │   └── ingestion_graph.py     # 摄入 StateGraph 构建
│       ├── retrieval/                  # 新增：检索模块
│       │   ├── __init__.py
│       │   ├── keywords.py            # LLM 关键词提取（ll_keywords + hl_keywords）
│       │   ├── search.py              # 三路搜索：local/global/naive
│       │   ├── context_builder.py     # 上下文构建 + 结构化输出
│       │   └── chunk_picker.py        # 加权轮询 chunk 选择器
│       ├── memory/                     # 三期新增：记忆模块
│       │   ├── __init__.py
│       │   ├── memory_manager.py      # MemoryManager：统筹提取/存储/检索/剪枝
│       │   ├── extractor.py           # 记忆提取：LLM 从对话中提取事实/偏好/模式
│       │   ├── retriever.py           # 记忆检索：时间加权 + 重要性加权融合
│       │   └── pruner.py             # 工作记忆剪枝：按 TTL 淘汰过期记忆
│       ├── eval/                       # 四期新增：自我评估模块
│       │   ├── __init__.py
│       │   ├── eval_manager.py        # EvalManager：统筹评估存储/检索/统计/维护
│       │   ├── evaluator.py           # run_evaluation()：LLM-as-Judge 异步三维度评估
│       │   ├── hard_case_miner.py     # generate_golden_answer()：难例金标答案生成
│       │   └── maintenance.py         # schedule_eval_maintenance()：后台清理过期记录
│       ├── llm/
│       │   ├── __init__.py
│       │   └── factory.py             # LLM 工厂（新增 create_embeddings）
│       ├── nodes/
│       │   ├── __init__.py
│       │   ├── supervisor.py          # Supervisor 节点
│       │   ├── retrieval_worker.py    # 检索 Worker（升级为 GraphRAG）
│       │   ├── code_worker.py         # 代码 Worker
│       │   ├── action_worker.py       # 动作 Worker
│       │   ├── summary_worker.py      # 汇总 Worker（注入 user_profile + memory context）
│       │   ├── refiner.py             # Refiner 节点
│       │   ├── load_memory.py         # 三期新增：加载用户画像和记忆节点
│       │   └── save_memory.py         # 三期新增：提取和存储记忆节点
│       └── sandbox/
│           ├── __init__.py
│           └── docker_sandbox.py      # Docker 代码沙箱
└── test/
    ├── __init__.py
    ├── conftest.py                     # pytest 夹具（新增 FakeEmbeddings、mock_embeddings）
    ├── mock_utils.py                   # 共享 mock（FakeLLM 支持 list 输入）
    └── api/
        ├── __init__.py
        ├── test_health.py              # 健康检查测试
        ├── test_chat.py                # 对话接口测试
        ├── test_documents.py           # 新增：文档管理 API 测试（9 个用例）
        ├── test_graphrag.py            # 新增：GraphRAG 组件测试（9 个用例）
        ├── test_memory.py               # 三期新增：记忆系统测试（23 个用例）
        └── test_eval.py                 # 四期新增：评估系统测试（26 个用例）
```

## 文件用途说明

### 配置文件

| 文件 | 用途 |
|------|------|
| `.env.example` | 提供环境变量的模板，部署时复制为 `.env` 并填入真实值 |
| `pytest.ini` | 配置 pytest 的 Python 路径和测试目录 |
| `requirements.txt` | 锁定 Python 依赖；二期新增 `faiss-cpu`、`networkx` |

### 应用层 (`app/`)

| 文件 | 用途 |
|------|------|
| `main.py` | FastAPI 应用工厂；lifespan 中初始化 `StorageManager`、`MemoryManager`、`EvalManager` 并注入图；启动 eval 后台维护任务 |
| `config/settings.py` | Pydantic Settings；二期新增 embedding/storage；三期新增记忆配置；四期新增 eval 配置（`eval_enabled` 等） |
| `domain/schemas.py` | 对话/文档/记忆/评估模型；四期新增 EvalRunItem、HardCaseItem、FeedbackRequest 等 9 个模型 |
| `api/routes/documents.py` | 文档管理 API：`POST /documents/ingest`、`GET /documents/stats`、`GET /documents`、`DELETE /documents/{doc_id}` |
| `api/routes/memory.py` | 三期新增：记忆管理 API：`GET /memory/{user_id}`、`DELETE /memory/{user_id}`、`GET /profile/{user_id}` |
| `api/routes/eval.py` | 四期新增：评估与反馈 API（10 个端点）：评估摘要/运行记录/难例管理/用户反馈 |

### 存储层 (`app/agent/storage/`) — 二期新增

| 文件 | 用途 |
|------|------|
| `vector_store.py` | `FAISSStore`：封装 `faiss.IndexFlatIP`，支持向量添加/检索/删除/持久化 |
| `graph_store.py` | `GraphStore`：封装 `NetworkX DiGraph`，支持节点/边的增删查和 pickle 持久化 |
| `kv_store.py` | `JsonKVStore`：JSON 文件 KV 存储，用于文档文本 chunk 的存取 |

### 文档摄入管道 (`app/agent/ingestion/`) — 二期新增

| 文件 | 用途 |
|------|------|
| `chunker.py` | `chunk_text()`：按段落优先分割文本，超长段落回退到固定窗口；支持重叠 |
| `extractor.py` | `extract_entities()`：LLM 抽取实体和关系，含多轮 gleaning；`json_repair` 容错解析 |
| `ingestion_graph.py` | LangGraph `StateGraph`：编排摄入流程（检查重复→分块→嵌入→实体抽取→存储→标记完成） |

### 检索模块 (`app/agent/retrieval/`) — 二期新增

| 文件 | 用途 |
|------|------|
| `keywords.py` | `extract_keywords()`：LLM 提取局部关键词（`ll_keywords`）和全局关键词（`hl_keywords`） |
| `search.py` | `local_search()` / `global_search()` / `naive_search()`：三路并行搜索实体/关系/文本向量库 |
| `chunk_picker.py` | `pick_by_weighted_polling()`：加权轮询选择器，按 4:3:3 比例从实体/关系/向量结果中选取 chunk |
| `context_builder.py` | `build_context()`：合并多源结果，生成结构化上下文文本供 LLM 使用 |

### 记忆模块 (`app/agent/memory/`) — 三期新增

| 文件 | 用途 |
|------|------|
| `memory_manager.py` | `MemoryManager`：统筹记忆提取/存储/检索/剪枝，管理 4 个存储后端 |
| `extractor.py` | `extract_memories_from_conversation()`：LLM 从对话中提取结构化记忆 |
| `retriever.py` | `format_memory_context()` / `format_profile_context()`：格式化为 prompt 可用文本 |
| `pruner.py` | `prune_expired_memories()` / `schedule_pruning()`：工作记忆 TTL 剪枝 |

### 评估模块 (`app/agent/eval/`) — 四期新增

| 文件 | 用途 |
|------|------|
| `eval_manager.py` | `EvalManager`：统筹评估存储/检索/统计/维护，管理 4 个 JsonKVStore 后端 |
| `evaluator.py` | `run_evaluation()`：LLM-as-Judge 异步三维度评估（faithfulness/relevance/completeness），解析评分并触发难例挖掘 |
| `hard_case_miner.py` | `generate_golden_answer()`：使用配置的强模型为低分回答生成金标答案 |
| `maintenance.py` | `schedule_eval_maintenance()`：后台定时清理过期评估记录并裁剪总数 |

### 存储管理器 (`app/agent/storage_manager.py`) — 二期新增

| 方法 | 用途 |
|------|------|
| `__init__()` | 创建 5 个存储后端实例（entities_vdb、relationships_vdb、chunks_vdb、graph、text_chunks_kv） |
| `initialize()` | 从磁盘加载所有存储 |
| `finalize()` | 持久化所有存储到磁盘 |
| `get_context()` | 返回存储实例字典供检索 Worker 使用 |
| `has_documents` | 判断是否已摄入文档 |

### 智能体核心 (`app/agent/`)

| 文件 | 用途 |
|------|------|
| `constants.py` | 新增 GraphRAG/记忆/评估常量（`EVAL_DIMENSIONS`、`EVAL_MAX_RECENT_RUNS` 等） |
| `exceptions.py` | 新增 `StorageError`、`IngestionError`、`MemoryError`、`EvalError` |
| `state.py` | 新增 `IngestionState`、`DocumentItem` TypedDict；`AgentState` 新增记忆字段 |
| `prompts.py` | 新增 `EVALUATOR_PROMPT`、`GOLDEN_ANSWER_PROMPT`；`SUPERVISOR_PROMPT` / `SUMMARY_PROMPT` 增加记忆注入 |
| `graph.py` | `build_agent_graph(storage_manager, memory_manager)` 接收两个管理器；新增 load_memory/save_memory 节点 |
| `nodes/load_memory.py` | 三期新增：加载用户画像和相关记忆注入 AgentState |
| `nodes/save_memory.py` | 三期新增：从对话中提取记忆、过滤重要性、存储并更新画像 |
| `nodes/retrieval_worker.py` | 升级为 GraphRAG 检索：关键词提取→三路搜索→上下文构建→LLM 回答；无文档时回退 LLM-only |
| `llm/factory.py` | 新增 `create_embeddings()`：创建 `OpenAIEmbeddings` 实例 |

### 测试 (`test/`)

| 文件 | 用途 |
|------|------|
| `conftest.py` | 新增 `FakeEmbeddings` 类、`mock_embeddings` 夹具 |
| `mock_utils.py` | `FakeLLM.invoke` 支持 list 输入；fallback 新增实体抽取响应 |
| `api/test_documents.py` | 9 个测试用例：文档摄入/重复检测/空内容校验/统计/列表/删除 |
| `api/test_graphrag.py` | 9 个测试用例：分块器/关键词提取/上下文构建/FAISSStore 操作 |
| `api/test_memory.py` | 23 个测试用例：MemoryManager/提取器/检索器/记忆 API/配置回退 |
| `api/test_eval.py` | 26 个测试用例：EvalManager CRUD/统计/难例/反馈/评估 API/配置回退/难例挖掘 |
