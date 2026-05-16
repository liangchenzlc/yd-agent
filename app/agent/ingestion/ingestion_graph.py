from __future__ import annotations

import hashlib
from typing import Any

from langgraph.graph import END, StateGraph

from app.agent.exceptions import StorageError
from app.agent.ingestion.chunker import chunk_text
from app.agent.llm.factory import create_embeddings, embed_documents_batched
from app.agent.state import IngestionState
from app.agent.storage_manager import StorageManager


def _compute_doc_id(content: str) -> str:
    """基于内容 MD5 生成文档 ID，用于内容去重。

    使用 MD5（而非 SHA256）是因为：
    1. 这里只需要内容指纹做去重，不涉及安全场景
    2. MD5 计算更快，截断前 16 字符进一步减少存储开销
    3. 哈希碰撞概率在实际数据集上可忽略
    """
    return hashlib.md5(content.encode("utf-8")).hexdigest()[:16]


def check_duplicates_node(storage: StorageManager) -> callable:
    """创建"去重检查"节点。

    返回闭包而非直接定义函数的原因：节点需要访问 storage 实例，
    而 storage 在 build_ingestion_graph 时才传入。
    每个闭包捕获一个 storage 引用，使节点函数签名保持 (state) -> dict 的纯净形式，
    符合 LangGraph 的节点签名约定。
    """
    def fn(state: IngestionState) -> dict:
        idx = state.get("current_index", 0)
        docs = state.get("documents", [])
        # 边界保护：所有文档处理完后不应再调用此节点
        if idx >= len(docs):
            return {}

        doc = docs[idx]
        doc_id = _compute_doc_id(doc["content"])
        # 在 KV 存储中查询 doc_meta 前缀，存在即说明已摄入过
        is_dup = storage.text_chunks_kv.get_by_id(f"doc_meta:{doc_id}") is not None

        return {
            "doc_id": doc_id,
            "content": doc["content"],
            "metadata": doc.get("metadata", {}),
            "is_duplicate": is_dup,
            "chunks": [],  # 清空上一轮的 chunks 状态，避免残留
        }

    return fn


def save_document_node(storage: StorageManager) -> callable:
    """创建"保存文档元数据"节点。

    只在 is_duplicate=False 时写入 doc_meta，确保只保存一次。
    此节点在 embed_chunks 之后执行，确保 doc_meta 只在 chunk 实际落盘后写入。
    """
    def fn(state: IngestionState) -> dict:
        if state.get("is_duplicate"):
            return {}
        doc_id = state.get("doc_id", "")
        if not doc_id:
            return {}
        storage.text_chunks_kv.upsert({f"doc_meta:{doc_id}": state.get("metadata", {})})
        return {}

    return fn


def chunk_document_node() -> callable:
    """创建"文档分块"节点。

    纯函数，不依赖 storage，因此不需要闭包捕获外部依赖。
    """
    def fn(state: IngestionState) -> dict:
        if state.get("is_duplicate"):
            return {}
        from app.agent.constants import CHUNK_OVERLAP, CHUNK_SIZE

        chunks = chunk_text(state["content"], chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        return {"chunks": chunks}

    return fn


def _rollback_embed(storage: StorageManager, ids: list[str], doc_id: str) -> None:
    """回滚 embed_chunks_node 的部分写入。

    当三个存储后端之一写入失败时，需要清理其他两个已经写入的数据，保持一致性。
    注意：这是一个尽力而为的回滚——如果回滚本身也失败，调用方只能记录错误并重试。
    """
    storage.chunks_vdb.delete(ids)
    storage.text_chunks_kv.mdelete([f"chunk:{cid}" for cid in ids])
    storage.bm25_store.delete(ids)


def embed_chunks_node(storage: StorageManager) -> callable:
    """创建"向量化嵌入"节点。

    将 chunks 分别写入三个存储后端：FAISS（向量搜索）、KV（文本缓存）、BM25（关键词搜索）。
    三个写入操作非原子性，因此用 try/except + _rollback_embed 做手动回滚。
    如果不用回滚，部分写入会导致脏数据：向量搜到了但文本找不到，或反之。
    """
    def fn(state: IngestionState) -> dict:
        if state.get("is_duplicate"):
            return {}
        chunks = state.get("chunks", [])
        if not chunks:
            return {}

        embeddings_api = create_embeddings()
        texts = [c["content"] for c in chunks]
        embedded = embed_documents_batched(embeddings_api, texts)

        # chunk ID 格式：doc_id + chunk_id，确保全局唯一，避免不同文档的 chunk 冲突
        ids = [f"{state['doc_id']}_{c['chunk_id']}" for c in chunks]
        metadatas = [{"doc_id": state["doc_id"], "chunk_index": c["index"]} for c in chunks]

        try:
            storage.chunks_vdb.add_texts(ids, texts, embedded, metadatas)

            kv_pairs = {f"chunk:{cid}": {"text": txt, "doc_id": state["doc_id"]} for cid, txt in zip(ids, texts)}
            storage.text_chunks_kv.mset(kv_pairs)

            storage.bm25_store.add_texts(ids, texts, metadatas)
        except Exception:
            _rollback_embed(storage, ids, state["doc_id"])
            raise

        return {}

    return fn


def mark_completed_node() -> callable:
    """创建"标记完成"节点：自增 current_index 并更新统计计数。"""
    def fn(state: IngestionState) -> dict:
        idx = state.get("current_index", 0)
        ingested = state.get("total_ingested", 0)
        skipped = state.get("total_skipped", 0)
        total_chunks = state.get("total_chunks", 0) + len(state.get("chunks", []))

        if state.get("is_duplicate"):
            skipped += 1
        else:
            ingested += 1

        return {
            "current_index": idx + 1,
            "total_ingested": ingested,
            "total_skipped": skipped,
            "total_chunks": total_chunks,
        }

    return fn


def should_continue(state: IngestionState) -> str:
    """判断是否还有下一个文档需要处理。

    返回字符串而非布尔值是因为 StateGraph 的 conditional_edges
    需要精确匹配路径名称（"next" / "done"）。
    """
    idx = state.get("current_index", 0)
    total = len(state.get("documents", []))
    if idx >= total:
        return "done"
    return "next"


def build_ingestion_graph(storage: StorageManager) -> StateGraph:
    """构建摄入 StateGraph。

    图拓扑（每文档迭代一次）：
    check_duplicates → [去重跳过 / 处理] → chunk_document → embed_chunks → save_document → mark_completed → [循环 / 结束]

    去重路径（is_duplicate=True）：check_duplicates → mark_completed（跳过所有处理节点）
    新文档路径（is_duplicate=False）：check_duplicates → chunk_document → embed_chunks → save_document → mark_completed

    save_document 放在 embed_chunks 之后的关键原因：
    如果 embed_chunks 失败（如 embedding 服务超时），chunk 数据未落盘，
    doc_meta 也未被写入。重试时 check_duplicates 找不到 doc_meta，
    会重新处理该文档，避免数据永久丢失。
    """
    builder = StateGraph(IngestionState)

    # 所有闭包节点捕获 storage 引用，确保节点函数签名符合 LangGraph 规范
    builder.add_node("check_duplicates", check_duplicates_node(storage))
    builder.add_node("chunk_document", chunk_document_node())
    builder.add_node("embed_chunks", embed_chunks_node(storage))
    builder.add_node("save_document", save_document_node(storage))
    builder.add_node("mark_completed", mark_completed_node())

    builder.set_entry_point("check_duplicates")

    # 条件边：重复文档直接跳 mark_completed，不走 chunk/embed/save 路径
    builder.add_conditional_edges(
        "check_duplicates",
        lambda s: "chunk_document" if not s.get("is_duplicate") else "mark_completed",
        {"chunk_document": "chunk_document", "mark_completed": "mark_completed"},
    )
    builder.add_edge("chunk_document", "embed_chunks")
    # save_document 在 embed_chunks 之后：doc_meta 只在 chunk 实际落盘后写入
    builder.add_edge("embed_chunks", "save_document")
    builder.add_edge("save_document", "mark_completed")
    # 循环边：处理完一个文档后决定继续处理下一个还是结束
    builder.add_conditional_edges(
        "mark_completed",
        should_continue,
        {"next": "check_duplicates", "done": END},
    )

    return builder.compile()
