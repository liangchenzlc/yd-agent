from __future__ import annotations

from typing import Any

from app.agent.llm.factory import create_embeddings, embed_documents_batched
from app.agent.storage.bm25_store import BM25Store
from app.agent.storage.vector_store import FAISSStore

# 向量相似度低阈值：FAISS 余弦相似度低于此值视为不匹配。
# 0.25 是一个经验值，在内部测试中能过滤掉约 80% 的不相关结果同时保留大部分相关结果。
# 此阈值对 embedding 模型敏感，更换 embedding 模型时应重新校准。
LOW_CONFIDENCE_THRESHOLD = 0.25


def _compute_embeddings(texts: list[str]) -> list[list[float]]:
    emb = create_embeddings()
    return embed_documents_batched(emb, texts) if texts else []


def vector_search(
    query: str,
    chunks_vdb: FAISSStore,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """向量检索：用问题嵌入检索 chunk 向量库。

    先计算查询向量，然后用带阈值的相似度搜索 + 低置信度降级兜底。
    top_k 默认 10（比 BM25 的 20 小）是因为向量检索精度通常高于 BM25，
    更少的 top_k 可以减少后续 RRF 融合和重排的计算量。
    """
    if chunks_vdb.is_empty():
        return []

    emb = _compute_embeddings([query])[0]
    return _search_with_low_confidence_fallback(chunks_vdb, emb, top_k)


def search_by_bm25(
    query: str,
    bm25_store: BM25Store,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """BM25 关键词检索。

    top_k 默认为 20（比向量搜索的 10 大），因为 BM25 精度较低，
    多召回一些由后续 RRF 和重排模型做二次筛选。
    """
    if bm25_store.is_empty():
        return []
    return bm25_store.search(query, k=top_k)


def _search_with_low_confidence_fallback(
    store: FAISSStore,
    embedding: list[float],
    top_k: int,
) -> list[dict[str, Any]]:
    """先用低阈值召回，无结果时降级为取最相似的 1 条并标记低置信度。

    设计原因：RAG 系统中"没有搜索结果"比"有低质量结果"更糟糕。
    没有结果时 LLM 倾向于回答"不知道"，但有低质量结果时 LLM 可能提取出有用信息。
    因此降级策略宁愿返回弱相关结果并打标，让下游 LLM 自行判断可用性。
    """
    results = store.similarity_search_by_vector(
        embedding,
        k=top_k,
        score_threshold=LOW_CONFIDENCE_THRESHOLD,
    )
    if results:
        return results

    # 降级：返回最相似的 1 条（不设阈值），打标让 LLM 自行判断
    fallback = store.similarity_search_by_vector(embedding, k=1, score_threshold=None)
    marked = []
    for item in fallback:
        item = dict(item)
        metadata = dict(item.get("metadata", {}))
        metadata["low_confidence"] = True
        item["metadata"] = metadata
        marked.append(item)
    return marked
