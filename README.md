# yd-Agent

企业级 AI 多智能体助手系统 — 基于 LangGraph 的多智能体编排 + GraphRAG 增强检索 + 长期记忆 + 自我评估闭环。

## 项目简介

yd-Agent 是一个四阶段演进的企业级 AI 助手系统，通过 Supervisor-Worker 多智能体协作模式处理复杂任务。系统集成 GraphRAG 知识库检索、用户长期记忆与画像、以及 LLM-as-Judge 异步评估体系，实现从对话到知识积累再到质量追踪的完整闭环。

### 核心能力

- **多智能体编排** — Supervisor 调度 4 个专业 Worker（检索/代码执行/API调用/汇总），Refiner 实时纠错重试
- **GraphRAG 增强检索** — 文档摄入 + 实体关系抽取 + FAISS 向量检索 + NetworkX 图检索，三路并行搜索
- **长期记忆与画像** — 跨会话用户记忆（事实/偏好/模式），时间+重要性加权检索，自动提取与剪枝
- **自我评估闭环** — LLM-as-Judge 异步三维度评估（忠实度/相关性/完整性），难例挖掘 + 金标答案，用户反馈收集

## 项目架构

```
                         ┌─────────────────────────┐
                         │      FastAPI Server       │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │      Supervisor          │
                         │  (调度决策 + 任务分解)     │
                         └───┬────┬────┬────┬──────┘
                             │    │    │    │
              ┌──────────────┼────┼────┼────┼──────────────┐
              │              │    │    │    │              │
    ┌─────────▼──┐  ┌───────▼─┐ ┌─▼──────▼─┐ ┌─────────▼──┐
    │ Retrieval  │  │  Code   │ │  Action  │ │  Summary   │
    │  Worker    │  │ Worker  │ │  Worker  │ │  Worker    │
    │ (GraphRAG) │  │(Docker) │ │(HTTP API)│ │ (回答汇总)   │
    └────────────┘  └─────────┘ └──────────┘ └─────┬──────┘
                                                    │
                          ┌─────────────────────────▼──┐
                          │        Refiner              │
                          │  (质量评分 + 重试决策)        │
                          └──────────┬──────────────────┘
                                     │
                          ┌──────────▼──────────────────┐
                          │      异步评估 (fire-forget)   │
                          │  LLM-as-Judge 三维度评分      │
                          │  难例挖掘 + 金标答案生成       │
                          └─────────────────────────────┘

工作流: load_memory → Supervisor → [Workers 并行] → Summary → Refiner → save_memory
         ▲                                                              │
         └──────────────── 评分 < 7 时重试 ─────────────────────────────┘
```

### 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 智能体框架 | LangGraph (StateGraph) |
| LLM | 通义千问 (DashScope / OpenAI 兼容 API) |
| 向量存储 | FAISS (IndexFlatIP) |
| 图存储 | NetworkX (DiGraph) |
| 嵌入模型 | text-embedding-v4 |
| 代码沙箱 | Docker |
| 配置管理 | Pydantic Settings |

## 快速开始

### 环境要求

- Python ≥ 3.12
- Docker (代码执行 Worker 需要)
- 通义千问 API Key (或其他 OpenAI 兼容 API)

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd yd-agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env
```

编辑 `.env` 文件，填入必要配置：

```ini
# 必填：LLM API Key
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3.6-flash

# 可选：服务配置
API_HOST=0.0.0.0
API_PORT=8000

# 可选：评估配置
EVAL_ENABLED=true
EVAL_GOLDEN_MODEL=qwen3.6-max     # 用更强模型生成金标答案（留空则跳过）
```

### 启动

```bash
# 开发模式（支持热重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动后访问 http://localhost:8000/docs 查看 Swagger API 文档。

### 验证

```bash
# 健康检查
curl http://localhost:8000/health

# 发送对话
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "user_id": "user1"}'

# 查看评估摘要
curl http://localhost:8000/eval/summary
```

## 项目结构

```
yd-agent/
├── .env.example                    # 环境变量模板
├── pytest.ini                      # pytest 配置
├── requirements.txt                # Python 依赖清单
├── README.md                       # 项目说明（本文件）
├── app/                            # 应用主目录
│   ├── main.py                     # FastAPI 入口，lifespan 初始化
│   ├── config/
│   │   └── settings.py             # Pydantic Settings 配置管理
│   ├── domain/
│   │   └── schemas.py              # Pydantic 请求/响应模型
│   ├── api/routes/
│   │   ├── health.py               # GET /health
│   │   ├── chat.py                 # POST /chat, /chat/stream
│   │   ├── documents.py            # 文档管理 API（摄入/统计/删除）
│   │   ├── memory.py               # 记忆管理 API
│   │   └── eval.py                 # 评估与反馈 API
│   └── agent/
│       ├── _version.py             # 版本号
│       ├── constants.py            # 全局常量
│       ├── exceptions.py           # 异常类定义
│       ├── state.py                # LangGraph State 定义
│       ├── prompts.py              # Prompt 模板集合
│       ├── graph.py                # StateGraph 构建与路由
│       ├── storage_manager.py      # 存储管理器（FAISS + NetworkX + JSON）
│       ├── storage/                # 存储层
│       │   ├── vector_store.py     # FAISS 向量存储
│       │   ├── graph_store.py      # NetworkX 图存储
│       │   └── kv_store.py         # JSON 文件 KV 存储
│       ├── ingestion/              # 文档摄入管道
│       │   ├── chunker.py          # 文本分块器
│       │   ├── extractor.py        # LLM 实体/关系抽取
│       │   └── ingestion_graph.py  # 摄入编排图
│       ├── retrieval/              # 检索模块
│       │   ├── keywords.py         # 关键词提取
│       │   ├── search.py           # 三路并行搜索
│       │   ├── context_builder.py  # 上下文构建
│       │   └── chunk_picker.py     # 加权轮询选择器
│       ├── memory/                 # 记忆模块
│       │   ├── memory_manager.py   # 记忆管理器
│       │   ├── extractor.py        # 记忆提取
│       │   ├── retriever.py        # 记忆检索
│       │   └── pruner.py           # 过期剪枝
│       ├── eval/                   # 评估模块
│       │   ├── eval_manager.py     # 评估管理器
│       │   ├── evaluator.py        # LLM-as-Judge 评估器
│       │   ├── hard_case_miner.py  # 难例金标生成
│       │   └── maintenance.py      # 后台维护任务
│       ├── llm/
│       │   └── factory.py          # LLM / Embeddings 工厂
│       ├── nodes/                  # 图节点实现
│       │   ├── supervisor.py       # 调度节点
│       │   ├── retrieval_worker.py # 检索 Worker
│       │   ├── code_worker.py      # 代码 Worker
│       │   ├── action_worker.py    # 动作 Worker
│       │   ├── summary_worker.py   # 汇总 Worker
│       │   ├── refiner.py          # 反思节点
│       │   ├── load_memory.py      # 记忆加载节点
│       │   └── save_memory.py      # 记忆保存节点
│       └── sandbox/
│           └── docker_sandbox.py   # Docker 代码沙箱
└── test/
    ├── conftest.py                 # pytest 夹具
    ├── mock_utils.py               # 共享 Mock 工具
    └── api/
        ├── test_health.py
        ├── test_chat.py
        ├── test_documents.py       # 文档管理测试
        ├── test_graphrag.py        # GraphRAG 组件测试
        ├── test_memory.py          # 记忆系统测试
        └── test_eval.py            # 评估系统测试
```

## API 端点

### 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/chat` | 非流式对话 |
| POST | `/chat/stream` | SSE 流式对话 |

### 文档管理 (GraphRAG)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/documents/ingest` | 文档摄入 |
| GET | `/documents/stats` | 文档库统计 |
| GET | `/documents` | 文档列表 |
| DELETE | `/documents/{doc_id}` | 删除文档 |

### 记忆管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/memory/{user_id}` | 获取用户记忆 |
| DELETE | `/memory/{user_id}` | 删除用户记忆 |
| GET | `/profile/{user_id}` | 获取用户画像 |

### 评估与反馈

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/eval/summary` | 评估统计摘要 |
| GET | `/eval/runs` | 评估记录列表 |
| GET | `/eval/runs/{run_id}` | 评估记录详情 |
| DELETE | `/eval/runs` | 清空评估记录 |
| GET | `/eval/hard-cases` | 难例列表 |
| GET | `/eval/hard-cases/{case_id}` | 难例详情 |
| PATCH | `/eval/hard-cases/{case_id}/review` | 标记难例已审核 |
| DELETE | `/eval/hard-cases` | 清空难例 |
| POST | `/feedback` | 提交用户反馈 |
| GET | `/feedback` | 反馈列表 |
| GET | `/feedback/stats` | 反馈统计 |

## 运行测试

```bash
# 运行全部测试
pytest test/ -v

# 按模块运行
pytest test/api/test_chat.py -v        # 对话测试
pytest test/api/test_documents.py -v   # 文档管理测试
pytest test/api/test_graphrag.py -v    # GraphRAG 组件测试
pytest test/api/test_memory.py -v      # 记忆系统测试
pytest test/api/test_eval.py -v        # 评估系统测试
```

## 配置参考

所有配置通过环境变量或 `.env` 文件设置：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LLM_API_KEY` | — | LLM API Key（必填） |
| `LLM_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | LLM API 地址 |
| `LLM_MODEL` | `qwen3.6-flash` | LLM 模型名称 |
| `API_HOST` | `0.0.0.0` | 服务监听地址 |
| `API_PORT` | `8000` | 服务端口 |
| `MAX_REFINEMENTS` | `2` | 最大反思重试次数 |
| `EMBEDDING_MODEL` | `text-embedding-v4` | 嵌入模型 |
| `STORAGE_DIR` | `./data/storage` | 数据存储目录 |
| `SANDBOX_IMAGE` | `python:3.12-slim` | Docker 沙箱镜像 |
| `CODE_TIMEOUT` | `30` | 代码执行超时（秒） |
| `WORKING_MEMORY_TTL_HOURS` | `24` | 工作记忆保留时间 |
| `MEMORY_EXTRACTION_ENABLED` | `true` | 是否启用记忆提取 |
| `EVAL_ENABLED` | `true` | 是否启用后台评估 |
| `EVAL_HARD_CASE_THRESHOLD` | `5` | 难例判定分数阈值 |
| `EVAL_GOLDEN_MODEL` | — | 金标答案生成模型（留空跳过） |
| `EVAL_RETENTION_DAYS` | `30` | 评估记录保留天数 |
| `EVAL_MAINTENANCE_INTERVAL_HOURS` | `6` | 维护任务间隔（小时） |

## License

MIT
