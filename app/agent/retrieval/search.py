from __future__ import annotations

from typing import Any

from app.agent.llm.factory import create_embeddings, embed_documents_batched
from app.agent.storage.vector_store import FAISSStore

LOW_CONFIDENCE_THRESHOLD = 0.25


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """批量嵌入文本。"""
    emb = create_embeddings()
    return embed_documents_batched(emb, texts) if texts else []


def local_search(
    keywords: list[str],
    entities_vdb: FAISSStore,
    top_k: int = 10,
) -> dict[str, list[dict]]:
    """局部搜索：用 ll_keywords 检索实体 VDB，获取实体和关联关系。"""
    if not keywords or entities_vdb.is_empty():
        return {"entities": [], "relations": []}

    query = " ".join(keywords)
    emb = _embed_texts([query])[0]
    results = _search_with_low_confidence_fallback(entities_vdb, emb, top_k)
    return {"entities": results, "relations": []}


def global_search(
    keywords: list[str],
    relationships_vdb: FAISSStore,
    top_k: int = 10,
) -> dict[str, list[dict]]:
    """全局搜索：用 hl_keywords 检索关系 VDB，获取关系和关联实体。"""
    if not keywords or relationships_vdb.is_empty():
        return {"entities": [], "relations": []}

    query = " ".join(keywords)
    emb = _embed_texts([query])[0]
    results = _search_with_low_confidence_fallback(relationships_vdb, emb, top_k)
    return {"entities": [], "relations": results}


def naive_search(
    query: str,
    chunks_vdb: FAISSStore,
    top_k: int = 10,
) -> list[dict]:
    """朴素搜索：直接用问题检索 chunk VDB。"""
    if chunks_vdb.is_empty():
        return []

    emb = _embed_texts([query])[0]
    return _search_with_low_confidence_fallback(chunks_vdb, emb, top_k)


def _search_with_low_confidence_fallback(
    store: FAISSStore,
    embedding: list[float],
    top_k: int,
) -> list[dict]:
    results = store.similarity_search_by_vector(
        embedding,
        k=top_k,
        score_threshold=LOW_CONFIDENCE_THRESHOLD,
    )
    if results:
        return results

    fallback = store.similarity_search_by_vector(embedding, k=1, score_threshold=None)
    marked = []
    for item in fallback:
        item = dict(item)
        metadata = dict(item.get("metadata", {}))
        metadata["low_confidence"] = True
        item["metadata"] = metadata
        marked.append(item)
    return marked
