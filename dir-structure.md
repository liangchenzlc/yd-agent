# yd-Agent 目录结构

## 项目概述

yd-Agent 是基于 LangGraph 的多智能体企业知识问答系统，支持 Web Chat、管理后台、GraphRAG 知识库检索、Docker 代码执行、文件工具、长期记忆和评估记录查询。

## 目录树

```text
yd-agent/
├── admin/                          # 管理后台 Vite + React + TypeScript 应用
├── .env.example                    # 环境变量模板
├── .gitignore                      # Git 忽略规则
├── dir-structure.md                # 目录结构说明
├── pytest.ini                      # pytest 配置
├── README.md                       # 项目说明
├── requirements.txt                # Python 依赖清单
├── front/                          # 用户端 Vite + React + TypeScript 应用
├── app/
│   ├── __init__.py
│   ├── api/
│   │   └── routes/
│   │       ├── user.py             # 用户端 API：/api/xx
│   │       └── admin.py            # 管理端 API：/api/admin/xx
│   ├── runtime.py                  # 初始化 Storage/Memory/Eval/Graph 并负责关闭持久化
│   ├── services/                   # 应用服务层
│   ├── web/                        # FastAPI 应用装配、认证、SQLite 数据层
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py             # Pydantic Settings 配置
│   ├── domain/
│   │   ├── __init__.py
│   │   └── llm_output.py           # LLM 结构化输出模型
│   └── agent/
│       ├── __init__.py
│       ├── _version.py             # 版本号
│       ├── constants.py            # GraphRAG、记忆、评估常量
│       ├── conversation.py         # 近期对话上下文格式化
│       ├── exceptions.py           # 异常类
│       ├── graph.py                # Agent StateGraph 构建
│       ├── prompts.py              # Prompt 模板
│       ├── state.py                # AgentState 与摄入状态定义
│       ├── storage_manager.py      # 存储上下文管理器
│       ├── eval/                   # 评估记录、难例、统计和维护
│       ├── ingestion/              # 文档分块、实体关系抽取和摄入图
│       ├── llm/                    # LLM 与 Embedding 工厂
│       ├── memory/                 # 长期记忆、用户画像、检索与剪枝
│       ├── nodes/                  # Supervisor、Worker、Refiner、记忆节点
│       ├── retrieval/              # GraphRAG 检索、上下文构建、chunk 选择
│       ├── sandbox/                # Docker 代码沙箱
│       ├── storage/                # FAISS、NetworkX、JSON KV 存储
│       └── tools/                  # ReAct 工具系统与 Bash/Docker/File/Search 工具
└── test/
    ├── __init__.py
    ├── conftest.py
    ├── helpers.py                  # 共享测试辅助函数
    ├── ingestion/                  # 摄入图测试
    ├── memory/                     # 记忆管理测试
    ├── retrieval/                  # 检索策略测试
    ├── storage/                    # 存储层测试
    ├── tools/                      # 工具层测试
    └── workers/                    # Worker 节点测试
```

## 关键模块说明

| 路径 | 用途 |
|------|------|
| `app/web/main.py` | FastAPI 应用入口，只负责初始化和挂载 API 路由 |
| `app/api/routes/user.py` | 用户端 API，统一使用 `/api/xx` 路径 |
| `app/api/routes/admin.py` | 管理端 API，统一使用 `/api/admin/xx` 路径，包含文档管理、问答日志、难例池、知识缺口和用户管理 |
| `app/web/db.py` | SQLite 数据层，保存用户、会话、消息、问答日志、文档记录、反馈和用户启停状态 |
| `app/services/documents.py` | 文档摄入、列表、统计、删除的共享服务 |
| `app/runtime.py` | 运行时上下文；统一初始化和持久化存储、记忆、评估、Agent 图 |
| `app/config/settings.py` | 环境变量配置，包含 LLM、Embedding、存储、记忆、Docker、评估配置 |
| `app/agent/graph.py` | 构建 `load_memory -> supervisor -> workers -> summary -> refiner -> save_memory` 工作流 |
| `app/agent/prompts.py` | Supervisor、Worker、Summary、Refiner、Evaluator 等 Prompt 模板 |
| `app/agent/conversation.py` | 将近期对话转换为 Prompt 可用上下文 |
| `app/agent/storage_manager.py` | 聚合 chunks/entities/relationships 向量库、知识图谱和文本 KV |
| `app/agent/storage/vector_store.py` | FAISS 向量存储，支持持久化、元数据删除、重复 ID 覆盖 |
| `app/agent/retrieval/search.py` | local/global/naive 三路检索，使用低阈值召回和低置信度兜底 |
| `app/agent/retrieval/chunk_picker.py` | 从实体元数据反查 chunk，并合并实体/关系/向量召回结果 |
| `app/agent/memory/memory_manager.py` | 核心记忆和工作记忆管理，按用户与会话保存记忆 |
| `app/agent/sandbox/docker_sandbox.py` | Docker 沙箱执行 Python 代码，处理 stdout/stderr、超时和清理 |
| `app/agent/tools/base.py` | `@as_tool`、`BaseTool`、`ToolRegistry` 和 ReAct 循环 |

## 文档文件

| 文件 | 用途 |
|------|------|
| `README.md` | 项目介绍、快速开始、配置参考和常用命令 |
| `dir-structure.md` | 当前目录结构和关键模块说明 |
| `.claude/skills/yd-agent-guide/SKILL.md` | 面向本项目的本地 Codex/Claude 技能说明 |

## 数据和知识库

| 路径 | 用途 |
|------|------|
| `data/storage/` | 本地持久化数据目录，包含 FAISS index、JSON KV、图数据和评估记录 |
| `knowledge/` | 本地知识库示例文档，可通过管理后台或 API 摄入 |
| `docs/` | 项目外的资料或示例文档，不属于运行时代码 |

## 测试目录

| 路径 | 用途 |
|------|------|
| `test/ingestion/` | ingestion graph 的重复判断和状态清理测试 |
| `test/memory/` | 记忆 ID 唯一化和存储行为测试 |
| `test/retrieval/` | chunk 反查、低阈值召回和低置信度兜底测试 |
| `test/storage/` | FAISS、StorageManager、GraphRAG 辅助测试 |
| `test/tools/` | File/Search/Docker/Bash 工具测试 |
| `test/workers/` | Supervisor、Worker、Refiner 路由和节点测试 |
