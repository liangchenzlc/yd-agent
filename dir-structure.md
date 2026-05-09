# yd-Agent 目录结构

## 项目概述

基于 LangGraph 的企业级 AI 多智能体 CLI 助手系统，支持 GraphRAG 增强检索、长期记忆和评估记录查询。

## 目录树

```
yd-Agent/
├── .env.example                        # 环境变量模板（LLM、Embedding、存储、评估等）
├── .gitignore                          # Git 忽略规则
├── cli-doc.md                          # CLI 命令文档
├── dir-structure.md                    # 目录结构说明（本文件）
├── plan.md                             # 四期工程整体规划
├── plan2.md                            # 二期 GraphRAG 详细实施计划
├── pytest.ini                          # pytest 配置
├── requirements.txt                    # Python 依赖清单
├── yd-agent                            # CLI 可执行入口脚本
├── app/
│   ├── __init__.py
│   ├── cli.py                          # argparse 命令解析 + rich 终端输出
│   ├── runtime.py                      # 初始化 Storage/Memory/Eval/Graph 并负责关闭持久化
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                 # Pydantic Settings 配置
│   ├── domain/
│   │   ├── __init__.py
│   │   └── llm_output.py               # LLM 结构化输出 Pydantic 模型
│   └── agent/
│       ├── __init__.py
│       ├── _version.py                 # 版本号
│       ├── constants.py                # GraphRAG、记忆、评估常量
│       ├── exceptions.py               # 异常类
│       ├── state.py                    # LangGraph 状态定义
│       ├── prompts.py                  # Prompt 模板
│       ├── graph.py                    # StateGraph 构建
│       ├── storage_manager.py          # 存储上下文管理器
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── vector_store.py         # FAISS 向量存储
│       │   ├── graph_store.py          # NetworkX 图存储
│       │   └── kv_store.py             # JSON 文件 KV 存储
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── chunker.py              # 文本分块器
│       │   ├── extractor.py            # 实体/关系抽取
│       │   └── ingestion_graph.py      # 摄入 StateGraph
│       ├── retrieval/
│       │   ├── __init__.py
│       │   ├── keywords.py             # 关键词提取
│       │   ├── search.py               # local/global/naive 三路搜索
│       │   ├── context_builder.py      # 上下文构建
│       │   └── chunk_picker.py         # 加权轮询 chunk 选择器
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── memory_manager.py       # 记忆管理器
│       │   ├── extractor.py            # 记忆提取
│       │   ├── retriever.py            # 记忆检索格式化
│       │   └── pruner.py               # 工作记忆剪枝
│       ├── eval/
│       │   ├── __init__.py
│       │   ├── eval_manager.py         # 评估记录、难例和统计管理
│       │   ├── evaluator.py            # LLM-as-Judge 评估器
│       │   ├── hard_case_miner.py      # 难例金标答案生成
│       │   └── maintenance.py          # 评估维护任务
│       ├── llm/
│       │   ├── __init__.py
│       │   └── factory.py              # LLM 与 Embedding 工厂
│       ├── nodes/
│       │   ├── __init__.py
│       │   ├── supervisor.py           # Supervisor 调度节点
│       │   ├── retrieval_worker.py     # 检索 Worker
│       │   ├── code_worker.py          # 代码 Worker
│       │   ├── docs_worker.py          # 文档/文件 Worker
│       │   ├── summary_worker.py       # 汇总 Worker
│       │   ├── refiner.py              # 反思节点
│       │   ├── load_memory.py          # 记忆加载节点
│       │   └── save_memory.py          # 记忆保存节点
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py                 # @as_tool、BaseTool、ToolRegistry、ReAct 循环
│       │   ├── bash_tool.py            # BashTool
│       │   ├── docker_sandbox_tool.py  # DockerSandBoxTool
│       │   ├── file_tool.py            # FileTool
│       │   └── search_tool.py          # SearchTool
│       └── sandbox/
│           ├── __init__.py
│           └── docker_sandbox.py       # Docker 代码沙箱
└── test/
    ├── __init__.py
    ├── conftest.py                     # pytest 夹具
    ├── cli/
    │   ├── test_cli_chat.py            # chat/doctor CLI 测试
    │   ├── test_cli_documents.py       # documents CLI 测试
    │   └── test_cli_memory_eval.py     # memory/profile/eval CLI 测试
    ├── storage/
    │   └── test_graphrag.py            # GraphRAG 分块、上下文和存储组件测试
    ├── tools/                          # 工具层测试
    └── workers/                        # Worker 节点测试
```

## 文件用途说明

### 配置文件

| 文件 | 用途 |
|------|------|
| `.env.example` | 环境变量模板，部署时复制为 `.env` 并填入真实值 |
| `pytest.ini` | 配置 pytest 的 Python 路径和测试目录 |
| `requirements.txt` | Python 依赖清单，包含 `rich`、LangGraph、FAISS、NetworkX 等 |
| `yd-agent` | CLI 可执行入口脚本，调用 `app.cli.main()` |
| `cli-doc.md` | CLI 命令、参数、输出和退出码文档 |

### 应用层 (`app/`)

| 文件 | 用途 |
|------|------|
| `cli.py` | CLI 主入口；定义 chat/documents/memory/profile/eval/doctor 子命令和 rich 输出 |
| `runtime.py` | CLI 运行时上下文；初始化并关闭 `StorageManager`、`MemoryManager`、`EvalManager` 和 Agent graph |
| `config/settings.py` | Pydantic Settings；管理 LLM、Embedding、存储、记忆、评估等配置 |
| `domain/llm_output.py` | LLM 结构化输出模型：SupervisorOutput、RefinerOutput、MemoryExtractionOutput、EvaluationOutput、KeywordOutput、EntityExtractionOutput |

### 智能体核心 (`app/agent/`)

| 文件 | 用途 |
|------|------|
| `graph.py` | `build_agent_graph(storage_manager, memory_manager)` 构建多智能体 StateGraph |
| `state.py` | `AgentState` 与摄入状态定义 |
| `storage_manager.py` | 管理向量、图、KV 存储后端 |
| `nodes/*` | Supervisor、Worker、Refiner、记忆加载/保存节点 |
| `tools/*` | ReAct 工具系统与 Bash/Docker/File/Search 工具 |
| `storage/*` | FAISS、NetworkX、JSON KV 存储实现 |
| `ingestion/*` | 文档分块、实体关系抽取和摄入编排 |
| `retrieval/*` | GraphRAG 检索与上下文构建 |
| `memory/*` | 长期记忆、用户画像、检索与剪枝 |
| `eval/*` | 评估记录、难例、统计和维护 |

### 测试 (`test/`)

| 文件 | 用途 |
|------|------|
| `cli/test_cli_chat.py` | `yd-agent chat`、`yd-agent doctor` 的 CLI 行为测试 |
| `cli/test_cli_documents.py` | `yd-agent documents` 的摄入、列表、统计、删除测试 |
| `cli/test_cli_memory_eval.py` | `yd-agent memory/profile/eval` 的 CLI 行为测试 |
| `storage/test_graphrag.py` | GraphRAG 分块、关键词、上下文和 FAISSStore 组件测试 |
| `tools/*` | 工具层单元测试 |
| `workers/*` | Worker 节点单元测试 |
| `storage/*` | 存储层单元测试 |
