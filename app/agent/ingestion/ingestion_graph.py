from __future__ import annotations

import hashlib
import json
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from app.agent.exceptions import IngestionError
from app.agent.ingestion.chunker import chunk_text
from app.agent.ingestion.extractor import extract_entities
from app.agent.llm.factory import create_embeddings, embed_documents_batched
from app.agent.storage_manager import StorageManager


class Document(TypedDict):
    id: str
    content: str
    metadata: dict


class IngestionState(TypedDict):
    documents: list[Document]  # 待处理的原始文档
    current_index: int  # 当前处理的文档索引
    doc_id: str  # 当前文档 ID
    content: str  # 当前文档内容
    metadata: dict  # 当前文档元数据
    is_duplicate: bool  # 是否为重复文档
    chunks: list[dict]  # 分块结果
    entities: list[dict]  # 抽取的实体
    relationships: list[dict]  # 抽取的关系
    total_ingested: int  # 已摄入文档数
    total_skipped: int  # 跳过的文档数
    total_chunks: int  # 总块数
    total_entities: int  # 总实体数
    total_relationships: int  # 总关系数
    error: str | None  # 错误信息


def _compute_doc_id(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()[:16]


def check_duplicates_node(storage: StorageManager) -> callable:
    def fn(state: IngestionState) -> dict:
        idx = state.get("current_index", 0)
        docs = state.get("documents", [])
        if idx >= len(docs):
            return {}

        doc = docs[idx]
        doc_id = _compute_doc_id(doc["content"])
        is_dup = storage.text_chunks_kv.get_by_id(f"doc_meta:{doc_id}") is not None

        return {
            "doc_id": doc_id,
            "content": doc["content"],
            "metadata": doc.get("metadata", {}),
            "is_duplicate": is_dup,
            "chunks": [],
            "entities": [],
            "relationships": [],
        }

    return fn


def save_document_node(storage: StorageManager) -> callable:
    def fn(state: IngestionState) -> dict:
        if state.get("is_duplicate"):
            return {}
        doc_id = state["doc_id"]
        storage.text_chunks_kv.upsert({f"doc_meta:{doc_id}": state.get("metadata", {})})
        return {}

    return fn


def chunk_document_node() -> callable:
    def fn(state: IngestionState) -> dict:
        if state.get("is_duplicate"):
            return {}
        from app.agent.constants import CHUNK_OVERLAP, CHUNK_SIZE

        chunks = chunk_text(state["content"], chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        return {"chunks": chunks}

    return fn


def embed_chunks_node(storage: StorageManager) -> callable:
    def fn(state: IngestionState) -> dict:
        if state.get("is_duplicate"):
            return {}
        chunks = state.get("chunks", [])
        if not chunks:
            return {}

        embeddings_api = create_embeddings()
        texts = [c["content"] for c in chunks]
        embedded = embed_documents_batched(embeddings_api, texts)

        ids = [f"{state['doc_id']}_{c['chunk_id']}" for c in chunks]
        metadatas = [{"doc_id": state["doc_id"], "chunk_index": c["index"]} for c in chunks]

        storage.chunks_vdb.add_texts(ids, texts, embedded, metadatas)

        # 同时存储文本到 KV 供检索使用
        kv_pairs = {f"chunk:{cid}": {"text": txt, "doc_id": state["doc_id"]} for cid, txt in zip(ids, texts)}
        storage.text_chunks_kv.mset(kv_pairs)

        return {}

    return fn


def extract_entities_node(storage: StorageManager) -> callable:
    def fn(state: IngestionState) -> dict:
        if state.get("is_duplicate"):
            return {}
        chunks = state.get("chunks", [])
        if not chunks:
            return {"entities": [], "relationships": []}

        result = extract_entities(chunks)
        entities = result.get("entities", [])
        relationships = result.get("relationships", [])

        # 存储实体向量
        if entities:
            embeddings_api = create_embeddings()
            entity_texts = [e["name"] + ": " + e.get("description", "") for e in entities]
            entity_ids = [f"{state['doc_id']}_ent_{i}" for i in range(len(entities))]
            entity_embs = embed_documents_batched(embeddings_api, entity_texts)
            metadatas = [
                {
                    "doc_id": state["doc_id"],
                    "type": e.get("type", ""),
                    "source_id": e.get("source_id", ""),
                }
                for e in entities
            ]
            storage.entities_vdb.add_texts(entity_ids, entity_texts, entity_embs, metadatas)

            # 存储到图
            for e in entities:
                storage.graph.upsert_node(e["name"], {"type": e.get("type", ""), "description": e.get("description", "")})

        # 存储关系向量
        if relationships:
            embeddings_api = create_embeddings()
            rel_texts = [f"{r['source']} - {r['type']} -> {r['target']}: {r.get('description', '')}" for r in relationships]
            rel_ids = [f"{state['doc_id']}_rel_{i}" for i in range(len(relationships))]
            rel_embs = embed_documents_batched(embeddings_api, rel_texts)
            metadatas = [{"doc_id": state["doc_id"], "source": r["source"], "target": r["target"], "type": r["type"]} for r in relationships]
            storage.relationships_vdb.add_texts(rel_ids, rel_texts, rel_embs, metadatas)

            # 存储到图
            for r in relationships:
                storage.graph.upsert_edge(r["source"], r["target"], {"type": r["type"], "description": r.get("description", "")})

        return {"entities": entities, "relationships": relationships}

    return fn


def mark_completed_node() -> callable:
    def fn(state: IngestionState) -> dict:
        idx = state.get("current_index", 0)
        ingested = state.get("total_ingested", 0)
        skipped = state.get("total_skipped", 0)
        total_chunks = state.get("total_chunks", 0) + len(state.get("chunks", []))
        total_entities = state.get("total_entities", 0) + len(state.get("entities", []))
        total_relationships = state.get("total_relationships", 0) + len(state.get("relationships", []))

        if state.get("is_duplicate"):
            skipped += 1
        else:
            ingested += 1

        return {
            "current_index": idx + 1,
            "total_ingested": ingested,
            "total_skipped": skipped,
            "total_chunks": total_chunks,
            "total_entities": total_entities,
            "total_relationships": total_relationships,
        }

    return fn


def should_continue(state: IngestionState) -> str:
    """判断是否还有下一个文档需要处理。"""
    idx = state.get("current_index", 0)
    total = len(state.get("documents", []))
    if idx >= total:
        return "done"
    return "next"


def build_ingestion_graph(storage: StorageManager) -> StateGraph:
    """构建摄入 StateGraph。"""
    builder = StateGraph(IngestionState)

    builder.add_node("check_duplicates", check_duplicates_node(storage))
    builder.add_node("save_document", save_document_node(storage))
    builder.add_node("chunk_document", chunk_document_node())
    builder.add_node("embed_chunks", embed_chunks_node(storage))
    builder.add_node("extract_entities", extract_entities_node(storage))
    builder.add_node("mark_completed", mark_completed_node())

    builder.set_entry_point("check_duplicates")

    builder.add_conditional_edges(
        "check_duplicates",
        lambda s: "save_document" if not s.get("is_duplicate") else "mark_completed",
        {"save_document": "save_document", "mark_completed": "mark_completed"},
    )
    builder.add_edge("save_document", "chunk_document")
    builder.add_edge("chunk_document", "embed_chunks")
    builder.add_edge("embed_chunks", "extract_entities")
    builder.add_edge("extract_entities", "mark_completed")
    builder.add_conditional_edges(
        "mark_completed",
        should_continue,
        {"next": "check_duplicates", "done": END},
    )

    return builder.compile()
