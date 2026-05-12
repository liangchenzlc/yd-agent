---
name: yd-agent-guide
description: yd-agent 项目指南，覆盖当前 CLI 架构、技术栈、目录结构、开发约定和常用验证命令。
---

# yd-Agent 项目指南

## 项目定位

yd-Agent 是一个基于 LangGraph 的多智能体 CLI 助手系统。当前项目入口是 `yd-agent` 命令行工具，不是 FastAPI/IM Webhook 服务。

核心能力：

- CLI 对话：支持单轮 `yd-agent chat "消息"` 和连续对话 `yd-agent chat --interactive`
- 多智能体编排：`Supervisor -> Workers -> Summary -> Refiner -> save_memory`
- GraphRAG 检索：文档摄入、实体关系抽取、FAISS 向量检索、NetworkX 图存储、JSON KV 文本存储
- 代码执行：通过 Docker 沙箱运行 Python
- 文件工具：受工作区边界保护的读写和列表操作
- 长期记忆：核心记忆、工作记忆、用户画像和近期会话历史
- 评估记录：LLM-as-Judge 评分、难例记录和统计查询

## 当前技术栈

| 类别 | 技术 |
|------|------|
| CLI | argparse + Rich |
| 智能体编排 | LangGraph |
| LLM | OpenAI 兼容 API，默认 DashScope/qwen3.6-flash |
| Embedding | text-embedding-v4 |
| 向量存储 | FAISS IndexFlatIP |
| 图存储 | NetworkX DiGraph |
| KV 存储 | JSON 文件 |
| 代码沙箱 | Docker |
| 配置 | pydantic-settings |
| 测试 | pytest |

## 主要命令

```bash
yd-agent doctor
yd-agent chat "你好"
yd-agent chat --interactive
yd-agent documents ingest <path>
yd-agent documents list
yd-agent documents stats
yd-agent documents delete <doc_id> --yes
yd-agent memory list --user-id <user_id>
yd-agent memory clear --user-id <user_id> --yes
yd-agent profile show --user-id <user_id>
yd-agent eval summary
yd-agent eval runs
yd-agent eval hard-cases
```

完整命令以根目录 `cli-doc.md` 为准。

## 开发约定

- 新增 CLI 命令时同步更新 `cli-doc.md` 和 `README.md` 的常用命令。
- 新增文件或目录时同步更新 `dir-structure.md`。
- 修改配置项时同步更新 `.env.example` 和 `README.md` 配置参考。
- 修改文档摄入、检索、记忆或 Worker 路由时补对应测试。
- 不要把项目改回 FastAPI/IM API 架构，除非用户明确要求。
- 不要硬编码 supervisor 兜底意图规则；调度应通过 prompt 和结构化输出约束。
- 文档摄入涉及外部 Embedding/LLM API，真实运行会发送本地文档内容到配置的 API endpoint。

## 常用验证

```bash
python -m compileall app test
pytest test/cli test/retrieval test/memory test/ingestion test/storage/test_vector_store.py test/storage/test_storage_manager.py test/tools/test_file_tool.py test/tools/test_search_tool.py test/workers/test_supervisor.py test/workers/test_refinement_routing.py -q -p no:cacheprovider --basetemp .tmp_pytest
```

真实 Docker、真实 LLM、真实 Embedding 的测试可能依赖本机环境和网络，不应作为普通单元测试的唯一验证方式。
