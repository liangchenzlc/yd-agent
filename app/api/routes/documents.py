from fastapi import APIRouter, HTTPException

from app.agent.ingestion.chunker import chunk_text
from app.agent.ingestion.extractor import extract_entities
import hashlib

from app.agent.ingestion.ingestion_graph import Document
from app.agent.llm.factory import create_embeddings
from app.domain.schemas import (
    DocumentDeleteResponse,
    DocumentIngestItem,
    DocumentIngestRequest,
    DocumentIngestResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentStatsResponse,
)
router = APIRouter()


def _ensure_storage():
    """延迟导入避免循环引用。"""
    from app.main import get_storage_manager
    mgr = get_storage_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="存储管理器未初始化")
    return mgr


@router.post("/documents/ingest", response_model=DocumentIngestResponse)
async def ingest_documents(req: DocumentIngestRequest):
    """摄入文档 — 分块、抽取实体关系、向量嵌入、存储。"""
    mgr = _ensure_storage()
    storage_ctx = mgr.get_context()

    docs = [
        Document(id=d.id or hashlib.md5(d.content.encode("utf-8")).hexdigest()[:16], content=d.content, metadata=d.metadata)
        for d in req.documents
    ]

    total_ingested = 0
    total_skipped = 0
    total_chunks = 0
    total_entities = 0
    total_relationships = 0

    for doc in docs:
        doc_id = doc["id"]
        # 检查重复
        if storage_ctx["text_chunks_kv"].get_by_id(f"doc_meta:{doc_id}") is not None:
            total_skipped += 1
            continue

        # 分块
        chunks = chunk_text(doc["content"])
        texts = [c["content"] for c in chunks]
        if not texts:
            total_skipped += 1
            continue

        # 嵌入
        embeddings_api = create_embeddings()
        embedded = embeddings_api.embed_documents(texts)

        # 存储 chunks
        chunk_ids = [f"{doc_id}_{c['chunk_id']}" for c in chunks]
        metadatas = [{"doc_id": doc_id, "chunk_index": c["index"]} for c in chunks]
        storage_ctx["chunks_vdb"].add_texts(chunk_ids, texts, embedded, metadatas)
        kv_pairs = {
            f"chunk:{cid}": {"text": txt, "doc_id": doc_id}
            for cid, txt in zip(chunk_ids, texts)
        }
        storage_ctx["text_chunks_kv"].mset(kv_pairs)
        total_chunks += len(chunks)

        # 实体抽取
        result = extract_entities(chunks)
        entities = result.get("entities", [])
        relationships = result.get("relationships", [])

        if entities:
            entity_texts = [f"{e['name']}: {e.get('description', '')}" for e in entities]
            entity_ids = [f"{doc_id}_ent_{i}" for i in range(len(entities))]
            entity_embs = embeddings_api.embed_documents(entity_texts)
            ent_metadatas = [{"doc_id": doc_id, "type": e.get("type", ""), "source_id": e.get("source_id", "")} for e in entities]
            storage_ctx["entities_vdb"].add_texts(entity_ids, entity_texts, entity_embs, ent_metadatas)
            for e in entities:
                storage_ctx["graph"].upsert_node(e["name"], {"type": e.get("type", ""), "description": e.get("description", "")})

        if relationships:
            rel_texts = [f"{r['source']} - {r['type']} -> {r['target']}" for r in relationships]
            rel_ids = [f"{doc_id}_rel_{i}" for i in range(len(relationships))]
            rel_embs = embeddings_api.embed_documents(rel_texts)
            rel_metadatas = [{"doc_id": doc_id, "source": r["source"], "target": r["target"], "type": r["type"]} for r in relationships]
            storage_ctx["relationships_vdb"].add_texts(rel_ids, rel_texts, rel_embs, rel_metadatas)
            for r in relationships:
                storage_ctx["graph"].upsert_edge(r["source"], r["target"], {"type": r["type"], "description": r.get("description", "")})

        # 存储文档元数据
        storage_ctx["text_chunks_kv"].upsert({f"doc_meta:{doc_id}": doc["metadata"]})

        total_ingested += 1
        total_entities += len(entities)
        total_relationships += len(relationships)

    # 持久化
    await mgr.finalize()

    return DocumentIngestResponse(
        ingested=total_ingested,
        skipped=total_skipped,
        total_chunks=total_chunks,
        total_entities=total_entities,
        total_relationships=total_relationships,
    )


@router.get("/documents/stats", response_model=DocumentStatsResponse)
async def document_stats():
    """获取文档统计信息。"""
    mgr = _ensure_storage()
    storage_ctx = mgr.get_context()

    total_documents = len(storage_ctx["text_chunks_kv"].keys())
    total_entities = len(storage_ctx["entities_vdb"])
    total_relationships = len(storage_ctx["relationships_vdb"])
    total_chunks = len(storage_ctx["chunks_vdb"])

    return DocumentStatsResponse(
        total_documents=total_documents,
        total_chunks=total_chunks,
        total_entities=total_entities,
        total_relationships=total_relationships,
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    """列出所有文档。"""
    mgr = _ensure_storage()
    storage_ctx = mgr.get_context()

    doc_keys = [k for k in storage_ctx["text_chunks_kv"].keys() if k.startswith("doc_meta:")]
    items = []
    for dk in doc_keys:
        doc_id = dk.replace("doc_meta:", "")
        items.append(
            DocumentListItem(
                id=doc_id,
                chunks=0,
                entities=0,
            )
        )

    return DocumentListResponse(documents=items)


@router.delete("/documents/{doc_id}", response_model=DocumentDeleteResponse)
async def delete_document(doc_id: str):
    """删除文档及关联数据。"""
    mgr = _ensure_storage()
    storage_ctx = mgr.get_context()

    # 删除文档元数据
    storage_ctx["text_chunks_kv"].mdelete([f"doc_meta:{doc_id}"])

    # 删除关联 chunk（通过 KV 中的 chunk 前缀）
    chunk_keys = [k for k in storage_ctx["text_chunks_kv"].keys() if k.startswith(f"chunk:{doc_id}_")]
    storage_ctx["text_chunks_kv"].mdelete(chunk_keys)

    # 注：FAISS 按 ID 删除为重建操作，此处简化处理
    # 实际部署可考虑重建索引

    return DocumentDeleteResponse(deleted=True)
