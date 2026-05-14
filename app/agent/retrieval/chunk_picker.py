from __future__ import annotations

from typing import Any

from app.agent.constants import GRAPH_FIELD_SEP


def collect_chunks_from_entities(
    entities: list[dict],
    text_chunks_store: Any,
) -> list[dict]:
    """从实体的 source_id 解析 chunk IDs 并获取文本。"""
    chunk_keys = set()
    for ent in entities:
        metadata = ent.get("metadata", {})
        source_id = metadata.get("source_id", "")
        doc_id = metadata.get("doc_id", "")
        if source_id:
            parts = source_id.split(GRAPH_FIELD_SEP)
            for part in parts:
                if not part.startswith("chunk_"):
                    continue
                chunk_keys.add(f"chunk:{part}")
                if doc_id:
                    chunk_keys.add(f"chunk:{doc_id}_{part}")

    chunks = []
    for key in chunk_keys:
        chunk_data = text_chunks_store.get_by_id(key)
        if chunk_data:
            chunks.append(chunk_data)
    return chunks


def collect_chunks_from_relations(
    relations: list[dict],
    text_chunks_store: Any,
) -> list[dict]:
    """从关系的 source_id 解析 chunk IDs 并获取文本。"""
    # 关系不直接关联 chunk，走空实现
    return []


def select_weighted_chunks(
    entity_chunks: list[dict],
    relation_chunks: list[dict],
    vector_chunks: list[dict],
    top_k: int = 20,
) -> list[dict]:
    """从多源候选块中按权重比例选择，优先覆盖实体/关系/向量三类来源。"""
    # 权重设计：实体匹配最精确（0.4），关系和向量辅助补充（各0.3），
    # 保证检索结果既有精确命中又有广泛覆盖
    all_sources = [
        (entity_chunks, 0.4),
        (relation_chunks, 0.3),
        (vector_chunks, 0.3),
    ]

    # 去重（同一段文本可能被多路检索同时召回）
    seen = set()
    result = []
    for source, ratio in all_sources:
        count = max(1, int(top_k * ratio))
        for chunk in source[:count]:
            # 用文本内容去重
            key = chunk.get("text", chunk.get("content", ""))
            if key and key not in seen:
                seen.add(key)
                result.append(chunk)

    # 如果还不够 top_k，从 vector_chunks 补
    if len(result) < top_k:
        for chunk in vector_chunks:
            key = chunk.get("text", chunk.get("content", ""))
            if key and key not in seen:
                seen.add(key)
                result.append(chunk)
            if len(result) >= top_k:
                break

    return result[:top_k]
