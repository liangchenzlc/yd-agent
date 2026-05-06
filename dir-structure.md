# yd-Agent 目录结构

## 项目概述
基于 LangGraph 的企业级 AI 多智能体助手系统。

## 目录树

```
yd-Agent/
├── .env.example                        # 环境变量模板（LLM 配置、服务端口等）
├── .gitignore                          # Git 忽略规则（__pycache__、.env、venv 等）
├── api-doc.md                          # API 接口文档
├── dir-structure.md                    # 目录结构说明（本文件）
├── pytest.ini                          # pytest 配置（pythonpath、testpaths、asyncio）
├── requirements.txt                    # Python 依赖清单
├── app/                                # 应用主目录
│   ├── __init__.py
│   ├── main.py                         # FastAPI 应用入口（创建 app、注册路由、启动图实例）
│   ├── config/                         # 配置模块
│   │   ├── __init__.py
│   │   └── settings.py                 # Pydantic Settings 配置类（LLM、服务、沙箱参数）
│   ├── domain/                         # 领域模型
│   │   ├── __init__.py
│   │   └── schemas.py                  # 请求/响应 Pydantic 模型（ChatRequest, ChatResponse 等）
│   ├── api/                            # API 层
│   │   ├── __init__.py
│   │   └── routes/                     # 路由模块
│   │       ├── __init__.py
│   │       ├── health.py               # GET /health 健康检查
│   │       └── chat.py                 # POST /chat 对话，POST /chat/stream 流式对话
│   └── agent/                          # 多智能体核心
│       ├── __init__.py
│       ├── _version.py                 # 版本号（0.1.0）
│       ├── constants.py                # 常量定义（Worker 名称、阈值、超时等）
│       ├── exceptions.py               # 自定义异常类（AgentError, LLMError, SandboxError 等）
│       ├── state.py                    # LangGraph 状态定义（AgentState, WorkerResult TypedDict）
│       ├── prompts.py                  # Prompt 模板（Supervisor、4 Worker、Refiner 共 6 套）
│       ├── graph.py                    # StateGraph 构建（节点注册、Send 并行分发、条件路由）
│       ├── llm/                        # LLM 工厂
│       │   ├── __init__.py
│       │   └── factory.py              # create_llm()，基于 langchain init_chat_model
│       ├── nodes/                      # 图节点
│       │   ├── __init__.py
│       │   ├── supervisor.py           # Supervisor 节点：意图分析 + 路由分发
│       │   ├── retrieval_worker.py     # 检索 Worker：知识检索（一期占位）
│       │   ├── code_worker.py          # 代码 Worker：LLM 生成代码 + Docker 沙箱执行
│       │   ├── action_worker.py        # 动作 Worker：LLM 生成 REST 规格 + httpx 调用
│       │   ├── summary_worker.py       # 汇总 Worker：聚合多 Worker 结果生成最终回答
│       │   └── refiner.py              # Refiner 节点：质量评估 + 反思重试决策
│       └── sandbox/                    # 代码沙箱
│           ├── __init__.py
│           └── docker_sandbox.py       # Docker 沙箱：在 python:3.12-slim 容器中执行代码
└── test/                               # 测试目录
    ├── __init__.py
    ├── conftest.py                     # pytest 夹具（环境变量、mock LLM、mock Docker）
    ├── mock_utils.py                   # 共享 mock 工具（FakeLLM、fake_run_code 等）
    └── api/                            # API 测试
        ├── __init__.py
        ├── test_health.py              # 测试 GET /health
        └── test_chat.py                # 测试 POST /chat、POST /chat/stream
```

## 文件用途说明

### 配置文件

| 文件 | 用途 |
|------|------|
| `.env.example` | 提供环境变量的模板，部署时复制为 `.env` 并填入真实值 |
| `pytest.ini` | 配置 pytest 的 Python 路径和测试目录 |
| `requirements.txt` | 锁定 Python 依赖（FastAPI、LangChain、LangGraph、httpx、docker-py 等） |

### 应用层 (`app/`)

| 文件 | 用途 |
|------|------|
| `main.py` | FastAPI 应用工厂函数 `create_app()`，通过 lifespan 预构建 LangGraph 实例 |
| `config/settings.py` | 使用 `pydantic-settings` 从 `.env` 文件和环境变量读取配置，`@lru_cache` 单例模式 |
| `domain/schemas.py` | 定义 API 的请求/响应数据模型，确保数据格式一致 |
| `api/routes/health.py` | 健康检查端点，返回服务状态和版本 |
| `api/routes/chat.py` | 核心对话端点：非流式 `/chat` 和 SSE 流式 `/chat/stream`，调用 LangGraph 执行多智能体编排 |

### 智能体核心 (`app/agent/`)

| 文件 | 用途 |
|------|------|
| `state.py` | 定义 `AgentState` 和 `WorkerResult` 两个 TypedDict，`worker_results` 使用 `operator.add` reducer 实现并行结果自动合并 |
| `prompts.py` | 6 套 Prompt 模板：Supervisor、Retrieval Worker、Code Worker、Action Worker、Summary Worker、Refiner |
| `graph.py` | 构建完整的 StateGraph：注册 7 个节点 → 设置入口 → Send API 并行分发 → 条件路由循环 |
| `llm/factory.py` | LLM 工厂函数，使用 `langchain.chat_models.init_chat_model` 创建 DashScope 兼容的 Chat Model |
| `nodes/supervisor.py` | Supervisor 节点：调用 LLM 分析用户意图 → 解析 JSON 输出 → 决定调度哪些 Worker |
| `nodes/retrieval_worker.py` | 检索 Worker（一期占位）：调用 LLM 进行知识检索 |
| `nodes/code_worker.py` | 代码 Worker：LLM 生成 Python 代码 → 提取代码块 → Docker 沙箱执行 → 返回 stdout/stderr |
| `nodes/action_worker.py` | 动作 Worker：LLM 生成 REST API 调用规格 → httpx 执行 → 返回结果 |
| `nodes/summary_worker.py` | 汇总 Worker：聚合所有 Worker 结果 → LLM 综合生成最终回答 |
| `nodes/refiner.py` | Refiner 节点：LLM 评估回答质量 → 评分低于 7 且未达上限时触发重试 |
| `sandbox/docker_sandbox.py` | Docker 代码执行沙箱：写入临时文件 → `docker run` → 捕获 stdout/stderr → 清理 |

### 测试 (`test/`)

| 文件 | 用途 |
|------|------|
| `conftest.py` | 全局 pytest 夹具：自动设置测试环境变量、提供 mock LLM/mock Docker/mock httpx |
| `mock_utils.py` | 共享 mock 工具类 `FakeLLM`（按顺序返回预设响应）和 `fake_run_code`（模拟 Docker 执行） |
| `api/test_health.py` | 验证 `/health` 返回状态 ok 和版本信息 |
| `api/test_chat.py` | 验证 `/chat` 正常对话、代码执行、空消息校验、`/chat/stream` SSE 流 |
