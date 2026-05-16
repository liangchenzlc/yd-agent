from __future__ import annotations

from typing import Any

from app.agent.ingestion.chunker import _estimate_tokens


def expand_neighbor_chunks(
    chunks: list[dict[str, Any]],
    text_chunks_kv: Any,
    window: int = 1,
) -> list[dict[str, Any]]:
    """为每个 chunk 补充相邻块（前 window / 后 window），弥补分片导致的上下文断裂。

    设计动机：chunk_text 按固定大小切分时，一个完整的段落可能被切到两个 chunk 中，
    单独的每个 chunk 都缺少上下文。补充相邻块后检索到的 chunk 能携带完整语义。

    相邻块标记为"前驱块"/"后继块"并放在主块的前后（用 --- 分隔），
    以便 LLM 区分主块和补充块的主次关系。
    """
    result = []
    for c in chunks:
        meta = c.get("metadata", {})
        doc_id = meta.get("doc_id", "")
        chunk_index = meta.get("chunk_index", None)
        if doc_id and chunk_index is not None:
            prefix_parts = []
            suffix_parts = []
            for offset in range(1, window + 1):
                prev_text = _get_chunk_by_index(text_chunks_kv, doc_id, chunk_index - offset)
                if prev_text:
                    prefix_parts.insert(0, prev_text)
                next_text = _get_chunk_by_index(text_chunks_kv, doc_id, chunk_index + offset)
                if next_text:
                    suffix_parts.append(next_text)

            text = c.get("text", c.get("content", ""))
            if prefix_parts:
                text = "[前驱块]\n" + "\n\n".join(prefix_parts) + "\n---\n" + text
            if suffix_parts:
                text = text + "\n---\n[后继块]\n" + "\n\n".join(suffix_parts)

            c = dict(c)
            c["text"] = text

        result.append(c)
    return result


def _get_chunk_by_index(kv: Any, doc_id: str, chunk_index: int) -> str | None:
    """从 KV 存储中按文档 ID + 块索引加载相邻块文本。

    chunk_id 格式约定：chunk:{doc_id}_chunk_{index:06d}。
    必须与 ingestion_graph.py 中 embed_chunks_node 写入的 kv_pairs 格式一致，
    否则相邻块找不到，该功能静默失效（不报错但无效果）。
    """
    chunk_id = f"chunk:{doc_id}_chunk_{chunk_index:06d}"
    data = kv.get_by_id(chunk_id)
    return data.get("text") if data else None


def build_context(
    query: str,
    chunks: list[dict[str, Any]],
    max_tokens: int = 3000,
) -> tuple[str, dict[str, Any]]:
    """构建检索上下文文本，仅包含文档片段。

    使用 token 感知截断：chunks 已按 rerank_score 降序排列，
    从最高分开始填充，超出 max_tokens 时丢弃低分 chunk。
    至少保留一条 chunk，避免 LLM 上下文为空。
    """
    context_parts = []

    if chunks:
        # Token 感知截断：chunks 已按 rerank_score 降序排列
        selected = []
        total_tokens = 0
        for c in chunks:
            text = c.get("text", c.get("content", ""))
            if not text:
                continue
            tokens = _estimate_tokens(text)
            # 至少保留一个 chunk：即使第一个 chunk 超出 max_tokens 也要保留，
            # 否则 LLM 上下文完全为空，比超长上下文更糟糕
            if not selected and total_tokens + tokens > max_tokens:
                selected.append(c)
                total_tokens += tokens
                break
            if selected and total_tokens + tokens > max_tokens:
                break
            selected.append(c)
            total_tokens += tokens

        chunk_lines = []
        for c in selected:
            text = c.get("text", c.get("content", ""))
            if text:
                meta = c.get("metadata", {})
                tags = []
                ft = meta.get("file_type", "")
                if ft:
                    tags.append(ft)
                hp = meta.get("header_path", "")
                if hp:
                    tags.append(hp)
                prefix = f"[{' | '.join(tags)}] " if tags else ""
                chunk_lines.append(f"---\n{prefix}{text}")
        context_parts.append("## 相关文档片段\n" + "\n".join(chunk_lines))

    context_str = "\n\n".join(context_parts)

    raw_data: dict[str, Any] = {
        "query": query,
        "chunk_count": len(chunks),
    }

    return context_str, raw_data
