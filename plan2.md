# 第二期：GraphRAG 增强推理实施计划

## 背景

一期已完成 Supervisor + 4 Worker + Refiner 多智能体编排。`retrieval_worker` 目前是 LLM 占位实现（直接调 LLM 回答），二期将其升级为真正的 GraphRAG 检索系统。

基于 hotShop-RAG 的成熟 GraphRAG 模式（FAISS + NetworkX + 关键词多模式搜索），但独立实现，不复用 hotShop-RAG 的 storage 和 prompts 代码。Embedding 使用 DashScope 的 text-embedding-v4（1024 维，通过 OpenAI 兼容 API）。

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     文档摄入管道 (Ingestion)                      │
│                                                                  │
│  POST /documents/ingest                                          │
│       │                                                          │
│       ▼                                                          │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐  │
│  │ 文本分块  │ → │ 实体抽取  │ → │ 向量嵌入  │ → │ FAISS/Graph  │  │
│  │ chunker  │   │ extractor│   │ embed    │   │    存储       │  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────┘  │
│                                                                  │
│  输出: chunks_vdb + entities_vdb + relationships_vdb + graph     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     检索流程 ( Retrieval )                       │
│                                                                  │
│  Supervisor 调度 retrieval_worker                                │
│       │                                                          │
│       ▼                                                          │
│  ┌──────────────┐                                                │
│  │ 关键词提取    │  LLM: 提取 ll_keywords + hl_keywords           │
│  │ keywords.py  │                                                │
│  └──────┬───────┘                                                │
│         │                                                        │
│    ┌────┴────────────────────┐                                   │
│    ▼              ▼                    ▼                          │
│ ┌────────┐  ┌──────────┐  ┌──────────┐                          │
│ │ local  │  │ global   │  │  naive   │  并行搜索                  │
│ │ search │  │ search   │  │  search  │                          │
│ │实体VDB │  │关系VDB   │  │ 分块VDB  │                          │
│ └───┬────┘  └────┬─────┘  └────┬─────┘                          │
│     │            │              │                                 │
│     └────────────┴──────┬───────┘                                 │
│                         ▼                                        │
│                  ┌──────────────┐                                 │
│                  │ 上下文构建    │  weighted polling + 重排序       │
│                  │ context_bld  │                                 │
│                  └──────┬───────┘                                 │
│                         ▼                                        │
│              返回 worker_results → summary_worker                │
│                                                                  │
│  回退：如果 entities_vdb 为空（无文档），直接用 LLM 回答           │
└─────────────────────────────────────────────────────────────────┘
```

## 目录变更

### 新增文件（16 个）

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

### 修改文件（12 个）

| 文件 | 变更内容 |
|------|----------|
| `requirements.txt` | 添加 `faiss-cpu>=1.8.0`、`networkx>=3.3` |
| `app/config/settings.py` | 添加 `embedding_model`、`embedding_api_key`、`embedding_base_url`、`storage_dir` |
| `app/agent/constants.py` | 添加 `GRAPH_FIELD_SEP`、`DEFAULT_ENTITY_TYPES`、`DEFAULT_MAX_GLEANING`、chunk 参数 |
| `app/agent/exceptions.py` | 添加 `IngestionError`、`StorageError` |
| `app/agent/llm/factory.py` | 添加 `create_embeddings()` 函数 |
| `app/agent/prompts.py` | 新增摄入/检索相关 Prompt 模板（分块提取、关键词提取），更新 `RETRIEVAL_WORKER_PROMPT` |
| `app/agent/state.py` | 新增 `IngestionState`、`RetrievalState` TypedDict |
| `app/agent/nodes/retrieval_worker.py` | 重写：检查 VDB → GraphRAG 检索 → 上下文构建 → 输出结果 |
| `app/main.py` | lifespan 中初始化 storage_manager，注册 documents 路由 |
| `app/domain/schemas.py` | 添加 `DocumentIngestRequest`、`DocumentStatsResponse`、`DocumentItem` 等 |
| `api-doc.md` | 添加 `/documents/*` 端点文档 |
| `dir-structure.md` | 更新目录结构 |

## 详细设计

### 1. 存储层 (`app/agent/storage/`)

三个存储后端，与 hotShop-RAG 模式一致但独立实现：

**FAISSStore** (`vector_store.py`)
- 封装 `faiss.IndexFlatIP`（内积 = 余弦相似度，输入已 L2 归一化）
- `initialize()` — 从 disk 加载 `{namespace}_meta.json` + `{namespace}.faiss`
- `add_texts()` — 支持预计算 embedding 传入，避免重复调用 embedding API
- `similarity_search_by_vector()` — 按 cosine threshold 过滤
- `delete()` — 支持按 ID 删除或清空全部
- `is_empty()` — 判断向量库是否为空（回退判断用）
- 持久化：`_persist()` 写 JSON + FAISS 文件到 `storage_dir`

**GraphStore** (`graph_store.py`)
- 封装 `NetworkxEntityGraph`（内部是 `nx.DiGraph`）
- `upsert_node()` / `upsert_edge()` — 幂等写入
- `get_nodes_batch()` / `get_edges_batch()` — 批量查询
- `get_all_nodes()` / `get_all_edges()` — 全量导出
- `delete_node()` — 删除节点及关联边
- 持久化：pickle 到 `{namespace}.graph`

**JsonKVStore** (`kv_store.py`)
- 存储文档文本 chunk 的 JSON KV 存储
- `mget()` / `mset()` / `mdelete()` — 基础 KV 操作
- `get_by_id()` — 读取并 JSON 反序列化
- `upsert()` — 批量幂等写入
- 持久化：`{namespace}.json`

### 2. 文档摄入管道 (`app/agent/ingestion/`)

**chunker.py** — 文本分块器
- `chunk_text(text, chunk_size=1200, chunk_overlap=100)` → list of chunks
- 按段落优先分割，超长段落回退到固定窗口
- 输出 `{chunk_id, content, index}`

**extractor.py** — 实体/关系抽取
- 复用 hotShop-RAG 的 extractor 模式：
  - `EXTRACT_SYSTEM_PROMPT` + `EXTRACT_USER_PROMPT` → LLM 抽取实体和关系
  - `GLEAN_PROMPT` → 多轮 gleaning（默认 1 轮，可配置）
  - `extract_entities(llm_invoke, chunks, entity_types)` → `{entities, relationships}`
- `_parse_extraction_result()` — json_repair 容错解析
- `_merge_entities()` — 同实体多 chunk 合并，source_id 用 `<SEP>` 拼接
- `_deduplicate_relationships()` — 去重对称关系

**ingestion_graph.py** — 摄入 StateGraph
```
check_duplicates → save_document → chunk_document → embed_chunks → store_chunks
                                                     ↘ extract_entities → store_entities
                                                                        → store_relationships
                                                     → mark_completed
```
- 每个文档生成 `doc_id`（基于内容的 MD5）
- `check_duplicates` — 检查是否已存在
- chunk → embedding 后存入 `chunks_vdb` + `text_chunks_kv`
- 实体存入 `entities_vdb` + `graph`
- 关系存入 `relationships_vdb` + `graph`

### 3. 检索升级 (`app/agent/retrieval/`)

**keywords.py** — LLM 关键词提取
- Prompt：输入用户问题 → 输出 `ll_keywords`（局部搜索，面向实体） + `hl_keywords`（全局搜索，面向关系）
- 使用 json_repair 容错解析

**search.py** — 三路并行搜索
- `local_search` → `entities_vdb.similarity_search_by_vector(ll_emb)` → 获取实体 + 关联边
- `global_search` → `relationships_vdb.similarity_search_by_vector(hl_emb)` → 获取关系 + 关联实体
- `naive_search` → `chunks_vdb.similarity_search_by_vector(q_emb)` → 直接文本 chunk
- 这些是直接函数调用（无需单独 LangGraph 节点），在 retrieval_worker 中串行/并行执行

**chunk_picker.py** — 加权轮询选择器
- `collect_chunks_from_entities()` — 从实体 source_id 解析 chunk IDs
- `collect_chunks_from_relations()` — 从关系 source_id 解析 chunk IDs
- `pick_by_weighted_polling()` — 按 item 权重分配 chunk 名额

**context_builder.py** — 上下文构建
- `build_context(query, entities, relations, vector_chunks, text_chunks_store)` → `(context_str, raw_data)`
- 合并 entity/relation/vector 三种来源的 chunks
- 去重、截断（chunk_top_k=20）
- 生成结构化 context 文本（实体列表 + 关系列表 + 文本块）

### 4. retrieval_worker 重写

```
retrieval_worker_node(state):
    1. 检查 entities_vdb.is_empty() → 如果为空，回退到原 LLM-only 逻辑
    2. 调用 LLM 提取 ll_keywords + hl_keywords
    3. 并行执行：
       a. local_search(ll_keywords) → entities + relations
       b. global_search(hl_keywords) → entities + relations  
       c. naive_search(question) → vector_chunks
    4. 合并结果（去重 entities/relations）
    5. build_context() → 结构化 context
    6. 将 context 写入 worker_results
    7. summary_worker 利用 context 生成准确回答
```

关键：GraphRAG context 与现有的 SUMMARY_PROMPT 配合 —— retrieval_worker 返回的 `content` 中包含 `{context, entities, relationships}`，summary_worker 可直接使用。

### 5. 存储管理器 (`storage_manager.py`)

```python
class StorageManager:
    def __init__(self, storage_dir: str, embedding_model: str, ...):
        self.entities_vdb = FAISSStore("entities", storage_dir, embedding_dim=1024)
        self.relationships_vdb = FAISSStore("relationships", storage_dir, embedding_dim=1024)
        self.chunks_vdb = FAISSStore("chunks", storage_dir, embedding_dim=1024)
        self.graph = GraphStore("knowledge", storage_dir)
        self.text_chunks_kv = JsonKVStore("text_chunks", storage_dir)
    
    async def initialize(self): ...   # 加载所有存储
    async def finalize(self): ...     # 持久化所有存储
    def get_context(self) -> dict: ... # 返回检索所需的存储实例
```

生命周期绑定到 FastAPI lifespan，单例模式。

### 6. API 端点

**POST /documents/ingest**
```json
请求: {"documents": [{"id": "doc1", "content": "..."}, ...]}
响应: {"ingested": 3, "skipped": 1, "total_chunks": 42, "total_entities": 15}
```

**GET /documents/stats**
```json
响应: {"total_documents": 5, "total_chunks": 120, "total_entities": 45, "total_relationships": 30}
```

**GET /documents**
```json
响应: {"documents": [{"id": "doc1", "chunks": 12, "entities": 5}, ...]}
```

**DELETE /documents/{doc_id}**
```json
响应: {"deleted": true}
```

### 7. 配置新增

```python
# settings.py 新增
embedding_model: str = "text-embedding-v4"
embedding_api_key: str = ""
embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
storage_dir: str = "./data/storage"

# constants.py 新增
GRAPH_FIELD_SEP = "<SEP>"
DEFAULT_ENTITY_TYPES = ["person", "organization", "product", "concept", "location", "event", "technology"]
DEFAULT_MAX_GLEANING = 1
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 100
```

### 8. Embedding 工厂

```python
# factory.py 新增
def create_embeddings() -> OpenAIEmbeddings:
    from langchain_openai import OpenAIEmbeddings
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.embedding_base_url or settings.llm_base_url,
        api_key=settings.embedding_api_key or settings.llm_api_key,
    )
```

## 边界情况与回退

| 场景 | 处理方式 |
|------|----------|
| **无文档已摄入（VDB 为空）** | `retrieval_worker` 检测 `entities_vdb.is_empty()` → 回退到原 LLM-only 逻辑 |
| **LLM 抽取实体为空** | 至少使用 naive search 的 chunks |
| **实体/关系解析失败** | json_repair 修复，仍失败则返空列表，不阻断管道 |
| **Document 重复** | 按 `doc_id` 检查，已存在则 skip |
| **FAISS 文件损坏** | 捕获异常，重建空索引 |
| **Embedding API 故障** | 返回明确错误，不静默失败 |
| **存储目录不存在** | 自动创建 |

## 验证方式

1. `pytest test/ -v` — 全部测试通过（含一期已有 + 二期新增）
2. 启动服务：`uvicorn app.main:app --reload`
3. `curl http://localhost:8000/health` 返回 `{"status": "ok"}`
4. `curl -X POST http://localhost:8000/documents/ingest -d '{"documents":[{"id":"test","content":"...长文本..."}]}'` 返回摄入统计
5. `curl http://localhost:8000/documents/stats` 返回正确统计
6. `curl -X POST http://localhost:8000/chat -d '{"message":"关于...的问题"}'` retrieval_worker 返回基于文档的回答
7. 删除所有文档后，retrieval_worker 回退到 LLM-only 模式正常响应
8. 确认 `api-doc.md` 和 `dir-structure.md` 已更新
