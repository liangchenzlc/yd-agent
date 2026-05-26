# yd-Agent

企业级 AI 多智能体问答系统 — 基于 LangGraph 的多智能体编排 + GraphRAG 增强检索 + 长期记忆 + 自我评估闭环。

## 项目简介

yd-Agent 通过 **Supervisor-Worker** 多智能体协作模式处理复杂任务。系统集成 GraphRAG 知识库检索、用户长期记忆与画像、LLM-as-Judge 评估体系、以及数据库分析与图表生成能力，实现从 Web 问答到知识积累再到质量追踪的完整闭环。

## 核心能力

- **Web 企业问答** — 前后端分离架构，FastAPI 提供 REST API + SSE 流式推送，React 用户端提供登录和 Chat 页面。
- **企业管理后台** — 管理端支持文档管理、问答日志、难例池、知识缺口报表、用量统计、用户启停/角色维护和多租户管理。
- **多智能体编排** — Supervisor 调度 Retrieval、Data Analyst、Docs、Summary Worker，Refiner 负责质量检查和重试。
- **GraphRAG 增强检索** — 文档摄入、实体关系抽取、FAISS 向量检索、BM25 关键词检索 + RRF 融合 + Reranker 重排序。
- **数据库分析与图表生成** — Data Analyst Worker 通过 ReAct 循环自主查询数据库（MySQL/PostgreSQL/SQLite）并生成图表（Matplotlib/Plotly）。
- **长期记忆与画像** — 跨会话用户记忆（事实/偏好/行为模式/模板），按时间和重要性加权检索，自动提取、唯一化存储与 LRU 剪枝。
- **自我评估闭环** — LLM-as-Judge 三维度评估（忠实性/相关性/完整性），难例自动入库，定时评估维护。
- **多租户隔离** — 每个租户拥有独立的向量索引、BM25 倒排表、KV 存储和数据库记录。
- **用量统计** — 按日统计 API 调用次数和 LLM Token 消耗，支持 Redis 或 SQLite 后端。

## 项目架构

```
                          ┌─────────────────────────┐
                          │      Supervisor          │
                          │  (LLM 分析意图，调度决策)  │
                          └───┬────┬────┬────┬──────┘
                              │    │    │    │
               ┌──────────────┼────┼────┼────┼──────────────┐
               │              │    │    │    │              │
     ┌─────────▼──┐  ┌───────▼─┐ ┌─▼──────▼─┐ ┌─────────▼──┐
     │ Retrieval  │  │  Data   │ │   Docs   │ │  Summary   │
     │  Worker    │  │ Analyst │ │  Worker  │ │  Worker    │
     │(GraphRAG)  │  │ (SQL +  │ │ (File    │ │ (回答汇总)   │
     │            │  │  图表)   │ │  工具)    │ │            │
     └────────────┘  └─────────┘ └──────────┘ └─────┬──────┘
                                                     │
                           ┌─────────────────────────▼──┐
                           │        Refiner              │
                           │  (结构化评分 + 重试决策)      │
                           └──────────┬──────────────────┘
                                      │
                           ┌──────────▼──────────────────┐
                           │    记忆保存 / 评估记录查询     │
                           └─────────────────────────────┘

工作流: load_memory → Supervisor → [Workers 并行 ReAct] → Summary → Refiner → save_memory
          ▲                                                              │
          └──────────────── 需要改进时重试 ───────────────────────────────┘
```

### 文档摄入流程（独立 LangGraph）

```
文档上传 → check_duplicates (MD5 去重) → chunk_document (分块) 
                                          ↓
                                    embed_chunks (FAISS + BM25 + KV)
                                          ↓
                                    save_document → mark_completed
```

## 技术栈

| 层级 | 技术 |
|------|------|
| Web API | FastAPI + SQLite |
| 用户前端 | Vite + React + TypeScript + React Router + Redux Toolkit |
| 管理前端 | Vite + React + TypeScript + React Router + Redux Toolkit |
| 智能体框架 | LangGraph (StateGraph) + LangChain |
| LLM | 通义千问 (DashScope / OpenAI 兼容 API) |
| 向量存储 | FAISS (IndexFlatIP, 1024 维, L2 归一化内积 ≈ 余弦相似度) |
| 关键词检索 | BM25 (rank-bm25) |
| 重排序 | DashScope Rerank API |
| KV 存储 | Redis (替代文件存储) |
| 配置管理 | Pydantic Settings |
| 图表引擎 | Matplotlib + Plotly |
| 密码算法 | PBKDF2-SHA256 + JWT (pyjwt) |

## 快速开始

### 环境要求

- Python ≥ 3.12
- Redis（必需，替代文件存储）
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

编辑 `.env` 文件，填入必要配置（详见下方配置参考）。

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

后端只提供接口，不再渲染页面。首次启动自动初始化 default 租户和 `admin/admin` 管理员账号。

- 用户端前端：`http://127.0.0.1:5173` — 登录后进入 Chat
- 管理端前端：`http://127.0.0.1:5174` — 文档管理、问答日志、难例池、知识缺口、用户管理、租户管理、用量统计

### 启动前端（快速）

```bash
# 安装依赖并启动
cd front && npm install && npm run dev
cd admin && npm install && npm run dev
```

## API 参考

### 用户端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录（支持按租户登录） |
| GET | `/api/me` | 当前用户信息 |
| POST | `/api/chat` | 聊天（非流式） |
| GET | `/api/chat/stream` | SSE 流式聊天（实时推送 Agent 执行进度） |
| GET | `/api/sessions` | 会话列表 |
| GET | `/api/sessions/{session_id}/messages` | 会话消息 |
| DELETE | `/api/sessions/{session_id}` | 删除会话 |
| GET | `/api/documents` | 已摄入的文档列表 |
| POST | `/api/feedback` | 提交反馈（评分 -1/0/1 + 评论） |

### 管理端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/users` | 用户列表 |
| POST | `/api/admin/users` | 创建用户 |
| PATCH | `/api/admin/users/{user_id}` | 更新用户（启用/禁用） |
| GET | `/api/admin/documents` | 文档列表 |
| POST | `/api/admin/documents` | 上传文档（支持 PDF/TXT/MD/JSON/CSV/DOCX） |
| DELETE | `/api/admin/documents/{doc_id}` | 删除文档 |
| GET | `/api/admin/qa-logs` | 问答日志 |
| GET | `/api/admin/hard-cases` | 难例池 |
| GET | `/api/admin/knowledge-gaps` | 知识缺口报表 |
| GET | `/api/admin/usage` | 用量统计（按日 API 调用 + Token 消耗） |
| GET | `/api/admin/tenants` | 租户列表 |
| POST | `/api/admin/tenants` | 创建租户 |
| PATCH | `/api/admin/tenants/{tenant_id}` | 更新租户 |
| DELETE | `/api/admin/tenants/{tenant_id}` | 删除租户（级联删除关联数据） |

## Worker 详解

### Supervisor
LLM 分析用户意图，输出结构化决策（`SupervisorOutput`），决定调度哪些 Worker。支持 Refiner 反馈重定向。

### Retrieval Worker (GraphRAG)
通过 ReAct 循环调用 `SearchTool` 进行混合检索：
1. 向量搜索 (FAISS) + BM25 关键词搜索 **双路并行**
2. **RRF (Reciprocal Rank Fusion)** 融合结果
3. 元数据**后过滤**（如按文件类型筛选）
4. 候选少于 5 条时跳过 Rerank API，否则调用 DashScope Rerank
5. **邻近块补全**（恢复分片丢失的上下文）
6. Token 感知截断构建 LLM 上下文

### Data Analyst Worker
通过 ReAct 循环自主使用以下工具集：
- **DatabaseTool** — 列出表、查看表结构、预检 SQL、执行 SELECT 查询（多语句/写操作拦截）
- **ReportTool** — 生成柱状图/折线图/饼图/散点图/直方图（支持 Matplotlib PNG 和 Plotly HTML）

### Docs Worker
通过 ReAct 循环调用 `FileTool` 进行文档读写操作（写文件/读文件/列出目录），限于 `./docs` 目录。

### Summary Worker
聚合所有 Worker 结果（按轮次过滤），注入用户画像和记忆上下文，LLM 生成最终回答。

### Refiner
使用 `with_structured_output` 输出结构化评分（0-10），低于阈值且在最大重试次数内时，指定需重试的 Worker 并附带反馈。

## 工具系统

基于 `@as_tool` 装饰器和 `BaseTool` 基类，按能力域组织：

| 工具 | 方法数 | 功能 |
|------|--------|------|
| `SearchTool` | 1 | 知识库混合检索 |
| `DatabaseTool` | 4 | 数据库查询（只读） |
| `ReportTool` | 5 | 图表生成 |
| `FileTool` | 3 | 文档读写 |

所有工具通过 `ToolRegistry` 集中注册，`react_loop` / `areact_loop` 提供同步/异步 ReAct 执行循环。

## 项目结构

```
yd-agent/
├── admin/                          # 管理后台 Vite + React + TypeScript 应用
├── front/                          # 用户端 Vite + React + TypeScript 应用
├── app/
│   ├── api/routes/user.py          # 用户端 API
│   ├── api/routes/admin.py         # 管理端 API（含租户 CRUD）
│   ├── runtime.py                  # 运行时上下文（异步上下文管理器）
│   ├── web/
│   │   ├── main.py                 # FastAPI 应用装配 + CORS + 用量统计中间件
│   │   ├── auth.py                 # JWT 认证 + PBKDF2 密码哈希
│   │   ├── db.py                   # SQLite 数据层
│   │   ├── schemas.py              # Pydantic 请求/响应模型
│   │   └── chat_service.py         # Chat 服务（Redis 缓存历史 + Agent 编排）
│   ├── config/settings.py          # Pydantic Settings 配置管理
│   ├── domain/llm_output.py        # LLM 结构化输出模型
│   └── agent/
│       ├── graph.py                # 主 Agent StateGraph（含 Fan-out/Fan-in 路由）
│       ├── prompts.py              # 所有 Prompt 模板
│       ├── conversation.py         # 对话历史格式化
│       ├── constants.py            # 检索/记忆/评估常量
│       ├── state.py                # AgentState + IngestionState
│       ├── storage_manager.py      # 存储上下文管理器（单例缓存 + LRU 驱逐）
│       ├── nodes/                  # Supervisor / Retrieval / DataAnalyst / Docs / Summary / Refiner / Memory 节点
│       ├── retrieval/              # 搜索 + chunk 选取 + 上下文构建 + 重排序
│       ├── memory/                 # 长期记忆管理（提取/检索/剪枝）
│       ├── storage/                # FAISS + BM25 + Redis Cache + Redis KV
│       ├── ingestion/              # 文档分块 + 摄入 LangGraph
│       ├── eval/                   # LLM-as-Judge 评估 + 难例挖掘 + 维护任务
│       ├── tools/                  # SearchTool / DatabaseTool / ReportTool / FileTool + ReAct 循环
│       ├── llm/                    # LLM + Embedding 工厂
│       └── stats/                  # 用量统计（API 调用 + Token 消耗）
├── knowledge/                      # 知识库示例文档
├── test/                           # 测试（ingestion/memory/retrieval/storage/tools/workers）
└── data/
    ├── storage/                    # 持久化数据（FAISS index + web.db + 上传文件）
    └── charts/                     # 图表输出目录
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
| `RERANK_MODEL` | `qwen3-vl-rerank` | 重排序模型 |
| `RERANK_BASE_URL` | `https://dashscope.aliyuncs.com` | 重排序 API 地址 |
| `STORAGE_DIR` | `./data/storage` | 数据存储目录 |
| `WORKING_MEMORY_TTL_HOURS` | `24` | 工作记忆保留时间（小时） |
| `CORE_MEMORY_LIMIT` | `500` | 核心记忆数量上限 |
| `MEMORY_EXTRACTION_ENABLED` | `true` | 是否启用记忆提取 |
| `MEMORY_IMPORTANCE_THRESHOLD` | `0.3` | 记忆入库重要性阈值 |
| `EVAL_ENABLED` | `true` | 是否启用评估 |
| `EVAL_HARD_CASE_THRESHOLD` | `5` | 难例判定分数阈值 |
| `EVAL_GOLDEN_MODEL` | — | 金标答案生成模型（留空跳过） |
| `EVAL_RETENTION_DAYS` | `30` | 评估记录保留天数 |
| `EVAL_MAINTENANCE_INTERVAL_HOURS` | `6` | 评估维护任务间隔（小时） |
| `REDIS_HOST` | — | Redis 主机地址（必填，留空则禁用缓存） |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `REDIS_DB` | `0` | Redis 数据库编号 |
| `REDIS_PASSWORD` | — | Redis 密码 |
| `DB_TYPE` | `mysql` | 数据分析 Worker 数据库类型（mysql/postgresql/sqlite） |
| `DB_HOST` | `localhost` | 数据库主机地址 |
| `DB_PORT` | — | 数据库端口（默认 MySQL 3306 / PostgreSQL 5432） |
| `DB_USER` | — | 数据库用户 |
| `DB_PASSWORD` | — | 数据库密码 |
| `DB_DATABASE` | — | 数据库名 |
| `CHARTS_OUTPUT_DIR` | `./data/charts` | 图表输出目录 |
| `WEB_SECRET_KEY` | `change-me-in-production` | JWT 签名密钥（生产环境务必修改） |

## License

MIT
