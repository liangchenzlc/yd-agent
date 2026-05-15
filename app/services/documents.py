from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.agent.ingestion.chunker import chunk_text
from app.agent.ingestion.extractor import extract_entities
from app.agent.llm.factory import create_embeddings, embed_documents_batched


def compute_doc_id(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()[:16]


async def ingest_document(
    storage_manager: Any,
    path: Path,
    doc_id: str = "",
    *,
    chunker=chunk_text,
    entity_extractor=extract_entities,
    embeddings_factory=create_embeddings,
    embedder=embed_documents_batched,
) -> dict[str, Any]:
    """Ingest a local text document into the GraphRAG stores."""
    content = path.read_text(encoding="utf-8")
    resolved_doc_id = doc_id or compute_doc_id(content)
    storage_ctx = storage_manager.get_context()

    if storage_ctx["text_chunks_kv"].get_by_id(f"doc_meta:{resolved_doc_id}") is not None:
        return {
            "doc_id": resolved_doc_id,
            "ingested": 0,
            "skipped": 1,
            "total_chunks": 0,
            "total_entities": 0,
            "total_relationships": 0,
        }

    chunks = chunker(content)
    texts = [chunk["content"] for chunk in chunks]
    if not texts:
        return {
            "doc_id": resolved_doc_id,
            "ingested": 0,
            "skipped": 1,
            "total_chunks": 0,
            "total_entities": 0,
            "total_relationships": 0,
        }

    embeddings_api = embeddings_factory()
    embedded = embedder(embeddings_api, texts)
    chunk_ids = [f"{resolved_doc_id}_{chunk['chunk_id']}" for chunk in chunks]
    metadatas = [
        {
            "doc_id": resolved_doc_id,
            "chunk_index": chunk["index"],
            "source": str(path),
        }
        for chunk in chunks
    ]

    result = entity_extractor(chunks)
    entities = result.get("entities", [])
    relationships = result.get("relationships", [])

    entity_texts: list[str] = []
    entity_ids: list[str] = []
    entity_embs: list[list[float]] = []
    entity_metas: list[dict[str, Any]] = []
    if entities:
        entity_texts = [f"{entity['name']}: {entity.get('description', '')}" for entity in entities]
        entity_ids = [f"{resolved_doc_id}_ent_{index}" for index in range(len(entities))]
        entity_embs = embedder(embeddings_api, entity_texts)
        entity_metas = [
            {
                "doc_id": resolved_doc_id,
                "type": entity.get("type", ""),
                "source_id": entity.get("source_id", ""),
                "source": str(path),
            }
            for entity in entities
        ]

    rel_texts: list[str] = []
    rel_ids: list[str] = []
    rel_embs: list[list[float]] = []
    rel_metas: list[dict[str, Any]] = []
    if relationships:
        rel_texts = [f"{rel['source']} - {rel['type']} -> {rel['target']}" for rel in relationships]
        rel_ids = [f"{resolved_doc_id}_rel_{index}" for index in range(len(relationships))]
        rel_embs = embedder(embeddings_api, rel_texts)
        rel_metas = [
            {
                "doc_id": resolved_doc_id,
                "source": rel["source"],
                "target": rel["target"],
                "type": rel["type"],
                "document_source": str(path),
            }
            for rel in relationships
        ]

    try:
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

        if entity_ids:
            storage_ctx["entities_vdb"].add_texts(entity_ids, entity_texts, entity_embs, entity_metas)
            for entity in entities:
                storage_ctx["graph"].upsert_node(
                    entity["name"],
                    {
                        "doc_id": resolved_doc_id,
                        "type": entity.get("type", ""),
                        "description": entity.get("description", ""),
                        "source": str(path),
                    },
                )

        if rel_ids:
            storage_ctx["relationships_vdb"].add_texts(rel_ids, rel_texts, rel_embs, rel_metas)
            for rel in relationships:
                storage_ctx["graph"].upsert_edge(
                    rel["source"],
                    rel["target"],
                    {
                        "doc_id": resolved_doc_id,
                        "type": rel["type"],
                        "description": rel.get("description", ""),
                        "source": str(path),
                    },
                )

        storage_ctx["text_chunks_kv"].upsert({f"doc_meta:{resolved_doc_id}": {"source": str(path)}})
    except Exception:
        rollback_document_writes(storage_ctx, resolved_doc_id)
        raise

    storage_manager.finalize()
    return {
        "doc_id": resolved_doc_id,
        "ingested": 1,
        "skipped": 0,
        "total_chunks": len(chunks),
        "total_entities": len(entities),
        "total_relationships": len(relationships),
    }


def list_documents(storage_manager: Any) -> list[dict[str, Any]]:
    storage_ctx = storage_manager.get_context()
    documents = []
    for doc_key in [key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith("doc_meta:")]:
        doc_id = doc_key.replace("doc_meta:", "")
        meta = storage_ctx["text_chunks_kv"].get_by_id(doc_key) or {}
        chunks = len([key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith(f"chunk:{doc_id}_")])
        entities = len(
            storage_ctx["entities_vdb"].get_meta_by_metadata_value("doc_id", doc_id)
        )
        documents.append(
            {
                "id": doc_id,
                "source": meta.get("source", ""),
                "chunks": chunks,
                "entities": entities,
            }
        )
    return documents


def document_stats(storage_manager: Any) -> dict[str, int]:
    storage_ctx = storage_manager.get_context()
    return {
        "total_documents": len([key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith("doc_meta:")]),
        "total_chunks": len(storage_ctx["chunks_vdb"]),
        "total_entities": len(storage_ctx["entities_vdb"]),
        "total_relationships": len(storage_ctx["relationships_vdb"]),
    }


async def delete_document(storage_manager: Any, doc_id: str) -> dict[str, Any]:
    storage_ctx = storage_manager.get_context()
    existed = storage_ctx["text_chunks_kv"].get_by_id(f"doc_meta:{doc_id}") is not None
    chunk_keys = [key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith(f"chunk:{doc_id}_")]

    storage_ctx["text_chunks_kv"].mdelete([f"doc_meta:{doc_id}"])
    storage_ctx["text_chunks_kv"].mdelete(chunk_keys)
    storage_ctx["chunks_vdb"].delete_by_metadata("doc_id", doc_id)
    storage_ctx["entities_vdb"].delete_by_metadata("doc_id", doc_id)
    storage_ctx["relationships_vdb"].delete_by_metadata("doc_id", doc_id)

    graph = storage_ctx["graph"]
    for node_id, data in list(graph.get_all_nodes()):
        if data.get("doc_id") == doc_id:
            graph.delete_node(node_id)

    storage_manager.finalize()
    return {"deleted": existed or bool(chunk_keys), "doc_id": doc_id}


def rollback_document_writes(storage_ctx: dict[str, Any], doc_id: str) -> None:
    chunk_keys = [key for key in storage_ctx["text_chunks_kv"].keys() if key.startswith(f"chunk:{doc_id}_")]
    storage_ctx["text_chunks_kv"].mdelete([f"doc_meta:{doc_id}"])
    storage_ctx["text_chunks_kv"].mdelete(chunk_keys)
    storage_ctx["chunks_vdb"].delete_by_metadata("doc_id", doc_id)
    storage_ctx["entities_vdb"].delete_by_metadata("doc_id", doc_id)
    storage_ctx["relationships_vdb"].delete_by_metadata("doc_id", doc_id)

    graph = storage_ctx["graph"]
    for node_id, data in list(graph.get_all_nodes()):
        if data.get("doc_id") == doc_id:
            graph.delete_node(node_id)
