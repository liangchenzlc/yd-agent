# yd-Agent

企业级 AI 多智能体命令行助手系统 — 基于 LangGraph 的多智能体编排 + GraphRAG 增强检索 + 长期记忆 + 自我评估闭环。

## 项目简介

yd-Agent 通过 Supervisor-Worker 多智能体协作模式处理复杂任务。系统集成 GraphRAG 知识库检索、用户长期记忆与画像、以及 LLM-as-Judge 评估体系，实现从对话到知识积累再到质量追踪的完整闭环。

## 核心能力

- **CLI 交互** — 通过 `yd-agent` 命令完成对话、文档管理、记忆管理、评估查询和环境检查。
- **多智能体编排** — Supervisor 调度 Retrieval、Code、Docs、Summary Worker，Refiner 负责质量检查和重试。
- **GraphRAG 增强检索** — 文档摄入、实体关系抽取、FAISS 向量检索、NetworkX 图检索和三路并行搜索。
- **长期记忆与画像** — 跨会话用户记忆，按时间和重要性加权检索，自动提取与剪枝。
- **自我评估闭环** — LLM-as-Judge 三维度评估，支持评估记录和难例查询。

## 项目架构

```
                         ┌─────────────────────────┐
                         │       yd-agent CLI       │
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
| CLI | argparse + rich |
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

确保项目根目录在 `PATH` 中，或将根目录下的 `yd-agent` 脚本复制到虚拟环境的可执行目录。

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
STORAGE_DIR=./data/storage
EVAL_ENABLED=true
```

### 常用命令

```bash
# 环境检查
yd-agent doctor

# 对话
yd-agent chat "你好" --user-id user1

# 结构化对话输出
yd-agent chat "你好" --user-id user1 --json

# 流式对话
yd-agent chat --stream "总结知识库内容" --user-id user1

# 摄入文档
yd-agent documents ingest docs/example.md --id example

# 查看文档库
yd-agent documents list
yd-agent documents stats

# 删除文档
yd-agent documents delete example --yes

# 记忆与画像
yd-agent memory list --user-id user1
yd-agent memory clear --user-id user1 --yes
yd-agent profile show --user-id user1

# 评估记录
yd-agent eval summary
yd-agent eval runs --limit 20
yd-agent eval hard-cases --reviewed all
```

完整命令说明见 [`cli-doc.md`](cli-doc.md)。

## 项目结构

```
yd-agent/
├── .env.example                    # 环境变量模板
├── cli-doc.md                      # CLI 命令文档
├── dir-structure.md                # 目录结构说明
├── pytest.ini                      # pytest 配置
├── requirements.txt                # Python 依赖清单
├── yd-agent                        # CLI 可执行入口脚本
├── app/
│   ├── cli.py                      # CLI 命令解析与 rich 输出
│   ├── runtime.py                  # 运行时初始化与资源关闭
│   ├── config/settings.py          # Pydantic Settings 配置管理
│   ├── domain/llm_output.py        # LLM 结构化输出模型
│   └── agent/                      # 多智能体核心、存储、检索、记忆、评估、工具
└── test/
    ├── cli/                        # CLI 单元测试
    ├── tools/                      # 工具层测试
    ├── workers/                    # Worker 节点测试
    └── storage/                    # 存储层测试
```

## 运行测试

```bash
pytest test/cli -v
pytest test/workers test/tools test/storage -v
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
| `STORAGE_DIR` | `./data/storage` | 数据存储目录 |
| `SANDBOX_IMAGE` | `python:3.12-slim` | Docker 沙箱镜像 |
| `CODE_TIMEOUT` | `30` | 代码执行超时（秒） |
| `WORKING_MEMORY_TTL_HOURS` | `24` | 工作记忆保留时间 |
| `MEMORY_EXTRACTION_ENABLED` | `true` | 是否启用记忆提取 |
| `EVAL_ENABLED` | `true` | 是否启用评估 |
| `EVAL_HARD_CASE_THRESHOLD` | `5` | 难例判定分数阈值 |
| `EVAL_GOLDEN_MODEL` | — | 金标答案生成模型（留空跳过） |
| `EVAL_RETENTION_DAYS` | `30` | 评估记录保留天数 |

## License

MIT
