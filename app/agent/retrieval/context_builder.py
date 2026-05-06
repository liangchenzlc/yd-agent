from __future__ import annotations

from typing import Any


def build_context(
    query: str,
    entities: list[dict],
    relations: list[dict],
    vector_chunks: list[dict],
    text_chunks_store: Any,
) -> tuple[str, dict]:
    """构建检索上下文文本。

    返回 (context_str, raw_data)
    """
    import json

    context_parts = []

    # 实体列表
    if entities:
        entity_lines = []
        for e in entities:
            meta = e.get("metadata", {})
            entity_lines.append(f"- {e.get('id', e.get('text', ''))} ({meta.get('type', 'unknown')})")
        context_parts.append("## 相关实体\n" + "\n".join(entity_lines))

    # 关系列表
    if relations:
        rel_lines = []
        for r in relations:
            meta = r.get("metadata", {})
            rel_lines.append(
                f"- {meta.get('source', '?')} --[{meta.get('type', '?')}]--> {meta.get('target', '?')}"
            )
        context_parts.append("## 相关关系\n" + "\n".join(rel_lines))

    # 文本块
    if vector_chunks:
        chunk_lines = []
        for c in vector_chunks[:20]:
            text = c.get("text", c.get("content", ""))
            if text:
                chunk_lines.append(f"---\n{text}")
        context_parts.append("## 相关文档片段\n" + "\n".join(chunk_lines))

    context_str = "\n\n".join(context_parts)

    raw_data = {
        "query": query,
        "entity_count": len(entities),
        "relation_count": len(relations),
        "chunk_count": len(vector_chunks),
    }

    return context_str, raw_data
