# yd-Agent

企业级 AI 多智能体问答系统 — 基于 LangGraph 的多智能体编排 + GraphRAG 增强检索 + 长期记忆 + 自我评估闭环。

## 项目简介

yd-Agent 通过 Supervisor-Worker 多智能体协作模式处理复杂任务。系统集成 GraphRAG 知识库检索、用户长期记忆与画像、以及 LLM-as-Judge 评估体系，实现从 Web 问答到知识积累再到质量追踪的完整闭环。

## 核心能力

- **Web 企业问答** — 采用前后端分离架构，FastAPI 提供接口，React 用户端提供登录和 Chat 页面。
- **企业管理后台** — 管理端支持文档管理、问答日志、难例池、知识缺口报表和用户启停/角色维护。
- **多智能体编排** — Supervisor 调度 Retrieval、Code、Docs、Summary Worker，Refiner 负责质量检查和重试。
- **GraphRAG 增强检索** — 文档摄入、实体关系抽取、FAISS 向量检索、NetworkX 图检索和 local/global/naive 三路搜索；检索采用低阈值召回 + 低置信度兜底。
- **长期记忆与画像** — 跨会话用户记忆，按时间和重要性加权检索，自动提取、唯一化存储与剪枝。
- **自我评估闭环** — LLM-as-Judge 三维度评估，支持评估记录和难例查询。

## 项目架构

```
                        ┌─────────────────────────┐
                        │      Supervisor          │
                        │  (调度决策 + 任务分解)     │
                        └───┬────┬────┬────┬──────┘
                            │    │    │    │
             ┌──────────────┼────┼────┼────┼──────────────┐
             │              │    │    │    │              │
   ┌─────────▼──┐  ┌───────▼─┐ ┌─▼──────▼─┐ ┌─────────▼──┐
   │ Retrieval  │  │  Code   │ │  Docs    │ │  Summary   │
   │  Worker    │  │ Worker  │ │ Worker   │ │  Worker    │
   │ (GraphRAG) │  │(Docker) │ │(Files)   │ │ (回答汇总)   │
   └────────────┘  └─────────┘ └──────────┘ └─────┬──────┘
                                                   │
                         ┌─────────────────────────▼──┐
                         │        Refiner              │
                         │  (质量评分 + 重试决策)        │
                         └──────────┬──────────────────┘
                                    │
                         ┌──────────▼──────────────────┐
                         │      记忆保存 / 评估记录查询    │
                         └─────────────────────────────┘

工作流: load_memory → Supervisor → [Workers 并行] → Summary → Refiner → save_memory
        ▲                                                              │
        └──────────────── 需要改进时重试 ───────────────────────────────┘
```

## 技术栈

| 层级 | 技术 |
|------|------|
| Web API | FastAPI + SQLite |
| 用户前端 | Vite + React + TypeScript + React Router + Redux Toolkit |
| 管理前端 | Vite + React + TypeScript + React Router + Redux Toolkit |
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
- Docker（代码执行 Worker 需要）
- 通义千问 API Key（或其他 OpenAI 兼容 API）

### 安装

```bash
git clone <repo-url>
cd yd-agent
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入必要配置：

```ini
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3.6-flash
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_API_KEY=sk-your-api-key-here
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_BATCH_SIZE=10
STORAGE_DIR=./data/storage
WORKING_MEMORY_TTL_HOURS=24
CORE_MEMORY_LIMIT=500
MEMORY_EXTRACTION_ENABLED=true
MEMORY_IMPORTANCE_THRESHOLD=0.3
EVAL_ENABLED=true
EVAL_HARD_CASE_THRESHOLD=5
EVAL_RETENTION_DAYS=30
EVAL_MAINTENANCE_INTERVAL_HOURS=6
```

### 启动服务

```bash
# 后端 API
uvicorn app.web.main:app --reload

# 用户端前端
cd front
npm install
npm run dev

# 管理端前端
cd admin
npm install
npm run dev
```

后端只提供接口，不再渲染页面。当前 MVP 会自动初始化 `admin/admin` 管理员账号。

用户端前端默认访问 `http://127.0.0.1:5173`，登录后进入 Chat。
管理端前端默认访问 `http://127.0.0.1:5174`，支持登录、文档列表、文档上传、文档删除、问答日志筛选、难例池、知识缺口报表和用户管理。

### Docker 部署

```bash
docker compose up -d
```

详细部署说明见 Docker Compose 配置文件。

### 当前 Web API

```text
POST /api/auth/login
GET  /api/me
POST /api/chat
GET  /api/sessions
GET  /api/sessions/{session_id}/messages
GET  /api/documents
POST /api/admin/documents
GET  /api/admin/documents
DELETE /api/admin/documents/{doc_id}
GET  /api/admin/qa-logs
GET  /api/admin/hard-cases
GET  /api/admin/knowledge-gaps
GET  /api/admin/users
POST /api/admin/users
PATCH /api/admin/users/{user_id}
POST /api/feedback
```

## 项目结构

```
yd-agent/
├── .env.example                    # 环境变量模板
├── dir-structure.md                # 目录结构说明
├── pytest.ini                      # pytest 配置
├── requirements.txt                # Python 依赖清单
├── front/                          # 用户端 React 应用
├── admin/                          # 管理后台 React 应用
├── app/
│   ├── api/routes/user.py          # 用户端 API
│   ├── api/routes/admin.py         # 管理端 API
│   ├── runtime.py                  # 运行时初始化与资源关闭
│   ├── web/                        # FastAPI 应用装配、认证、SQLite 数据层
│   ├── config/settings.py          # Pydantic Settings 配置管理
│   ├── domain/llm_output.py        # LLM 结构化输出模型
│   └── agent/                      # 多智能体核心、存储、检索、记忆、评估、工具
└── test/
    ├── ingestion/                  # 摄入图测试
    ├── memory/                     # 记忆管理测试
    ├── retrieval/                  # 检索策略测试
    ├── storage/                    # 存储层测试
    ├── tools/                      # 工具层测试
    └── workers/                    # Worker 节点测试
```

## 运行测试

```bash
pytest test/ -v
```

## 配置参考

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LLM_API_KEY` | — | LLM API Key |
| `LLM_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | LLM API 地址 |
| `LLM_MODEL` | `qwen3.6-flash` | LLM 模型名称 |
| `MAX_REFINEMENTS` | `2` | 最大反思重试次数 |
| `EMBEDDING_MODEL` | `text-embedding-v4` | 嵌入模型 |
| `EMBEDDING_API_KEY` | — | Embedding API Key |
| `EMBEDDING_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Embedding API 地址 |
| `EMBEDDING_BATCH_SIZE` | `10` | Embedding 批量请求大小 |
| `STORAGE_DIR` | `./data/storage` | 数据存储目录 |
| `SANDBOX_IMAGE` | `python:3.12-slim` | Docker 沙箱镜像 |
| `CODE_TIMEOUT` | `30` | 代码执行超时（秒） |
| `WORKING_MEMORY_TTL_HOURS` | `24` | 工作记忆保留时间 |
| `CORE_MEMORY_LIMIT` | `500` | 核心记忆数量上限 |
| `MEMORY_EXTRACTION_ENABLED` | `true` | 是否启用记忆提取 |
| `MEMORY_IMPORTANCE_THRESHOLD` | `0.3` | 记忆入库重要性阈值 |
| `EVAL_ENABLED` | `true` | 是否启用评估 |
| `EVAL_HARD_CASE_THRESHOLD` | `5` | 难例判定分数阈值 |
| `EVAL_GOLDEN_MODEL` | — | 金标答案生成模型（留空跳过） |
| `EVAL_RETENTION_DAYS` | `30` | 评估记录保留天数 |
| `EVAL_MAINTENANCE_INTERVAL_HOURS` | `6` | 评估维护任务间隔 |

## License

MIT
