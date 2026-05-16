from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from app.agent.ingestion.chunker import chunk_text
from app.agent.llm.factory import create_embeddings, embed_documents_batched
from app.services.parser import extract_text


def compute_doc_id(content: str) -> str:
    """基于内容计算 MD5 指纹，用于文档去重。

    与 ingestion_graph.py 中的 _compute_doc_id 保持一致的算法，
    确保文档通过 API 上传和通过 Graph 摄入使用同一种去重 ID。
    """
    return hashlib.md5(content.encode("utf-8")).hexdigest()[:16]


async def ingest_document(
    storage_manager: Any,
    path: Path,
    doc_id: str = "",
    *,
    chunker=chunk_text,
    embeddings_factory=create_embeddings,
    embedder=embed_documents_batched,
) -> dict[str, Any]:
    """将本地文档摄入到混合（向量 + BM25）存储中。

    支持格式：txt, md, json, csv, pdf, docx。
    如果文档已存在（通过 content MD5 检测），跳过处理。

    注入参数 chunker/embeddings_factory/embedder 的设计意图：
    便于单元测试时注入 mock，避免实际调用 LLM embedding API。
    """
    content, file_meta = extract_text(path)
    resolved_doc_id = doc_id or compute_doc_id(content)
    storage_ctx = storage_manager.get_context()

    # 去重检查：doc_meta 存在即说明已经摄入过
    if storage_ctx["text_chunks_kv"].get_by_id(f"doc_meta:{resolved_doc_id}") is not None:
        return {
            "doc_id": resolved_doc_id,
            "ingested": 0,
            "skipped": 1,
            "total_chunks": 0,
        }

    chunks = chunker(content)
    texts = [chunk["content"] for chunk in chunks]
    if not texts:
        return {
            "doc_id": resolved_doc_id,
            "ingested": 0,
            "skipped": 1,
            "total_chunks": 0,
        }

    # 异步执行 embedding 计算：embed_documents_batched 是同步阻塞调用，
    # 用 asyncio.to_thread 推送到线程池，避免阻塞 FastAPI 事件循环
    embeddings_api = embeddings_factory()
    embedded = await asyncio.to_thread(embedder, embeddings_api, texts)
    chunk_ids = [f"{resolved_doc_id}_{chunk['chunk_id']}" for chunk in chunks]
    metadatas = [
        {
            "doc_id": resolved_doc_id,
            "chunk_index": chunk["index"],
            "source": str(path),
            "file_type": file_meta.get("file_type", ""),
            "header_path": chunk.get("metadata", {}).get("header_path", ""),
        }
        for chunk in chunks
    ]

    try:
        # 依次写入三个存储后端，任一失败则触发回滚
        storage_ctx["chunks_vdb"].add_texts(chunk_ids, texts, embedded, metadatas)
        storage_ctx["text_chunks_kv"].mset(
            {
                f"chunk:{chunk_id}": {
                    "text": text,
                    "doc_id": resolved_doc_id,
                    "source": str(path),
                    "chunk_id": chunk_id,
                }
                for chunk_id, text in zip(chunk_ids, texts)
            }
        )
        storage_ctx["bm25_store"].add_texts(chunk_ids, texts, metadatas)

        # 最后写入 doc_meta，确保只有完整写入后才标记为已摄入
        storage_ctx["text_chunks_kv"].upsert({f"doc_meta:{resolved_doc_id}": {"source": str(path)}})
    except Exception:
        rollback_document_writes(storage_ctx, resolved_doc_id)
        raise

    return {
        "doc_id": resolved_doc_id,
        "ingested": 1,
        "skipped": 0,
        "total_chunks": len(chunks),
    }


def list_documents(storage_manager: Any) -> list[dict[str, Any]]:
    """列出所有已摄入的文档。

    扫描 KV 存储中 doc_meta 前缀的键，同时统计每个文档对应的 chunk 数量。
    注意：这是全表扫描，文档数量大时可能较慢，但管理后台的文档量通常在百级以内。
    """
    storage_ctx = storage_manager.get_context()
    documents = []
    for doc_key in [key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith("doc_meta:")]:
        doc_id = doc_key.replace("doc_meta:", "")
        meta = storage_ctx["text_chunks_kv"].get_by_id(doc_key) or {}
        chunks = len([key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith(f"chunk:{doc_id}_")])
        documents.append(
            {
                "id": doc_id,
                "source": meta.get("source", ""),
                "chunks": chunks,
            }
        )
    return documents


def document_stats(storage_manager: Any) -> dict[str, int]:
    """返回文档和 chunk 的统计数据。"""
    storage_ctx = storage_manager.get_context()
    return {
        "total_documents": len([key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith("doc_meta:")]),
        "total_chunks": len(storage_ctx["chunks_vdb"]),
    }


async def delete_document(storage_manager: Any, doc_id: str) -> dict[str, Any]:
    """从所有三个存储后端中删除文档及其所有 chunk。

    需要在 FAISS（向量）、KV（文本缓存）、BM25（关键词索引）三处同时删除。
    任何一处删除失败都不影响其他两处（尽力而为模式），
    因为残留的脏数据最多导致搜索返回空结果，不会系统崩溃。
    """
    storage_ctx = storage_manager.get_context()
    existed = storage_ctx["text_chunks_kv"].get_by_id(f"doc_meta:{doc_id}") is not None
    chunk_keys = [key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith(f"chunk:{doc_id}_")]

    storage_ctx["text_chunks_kv"].mdelete([f"doc_meta:{doc_id}"])
    storage_ctx["text_chunks_kv"].mdelete(chunk_keys)
    storage_ctx["chunks_vdb"].delete_by_metadata("doc_id", doc_id)
    storage_ctx["bm25_store"].delete_by_metadata("doc_id", doc_id)

    return {"deleted": existed or bool(chunk_keys), "doc_id": doc_id}


def rollback_document_writes(storage_ctx: dict[str, Any], doc_id: str) -> None:
    """回滚 ingest_document 的部分写入。

    当三个存储后端之一写入失败时，回滚其他两个已经成功写入的数据。
    回滚是"尽力而为"的——如果回滚本身也失败，只能记录错误并由运维手动清理。
    """
    chunk_keys = [key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith(f"chunk:{doc_id}_")]
    storage_ctx["text_chunks_kv"].mdelete([f"doc_meta:{doc_id}"])
    storage_ctx["text_chunks_kv"].mdelete(chunk_keys)
    storage_ctx["chunks_vdb"].delete_by_metadata("doc_id", doc_id)
    storage_ctx["bm25_store"].delete_by_metadata("doc_id", doc_id)
