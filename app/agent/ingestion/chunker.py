from __future__ import annotations

import re


def chunk_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 100) -> list[dict]:
    """将文本分割成重叠的块。

    优先按段落分割，超长段落回退到固定窗口。
    返回 [{"chunk_id": str, "content": str, "index": int}, ...]
    """
    if not text.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 如果单一段落超过 chunk_size，直接按窗口切分
        if len(para) > chunk_size:
            # 先 flush 当前累积
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            # 窗口切分长段落
            start = 0
            while start < len(para):
                end = start + chunk_size
                chunks.append(para[start:end])
                start = end - chunk_overlap if end < len(para) else len(para)
            continue

        if current_len + len(para) + 2 > chunk_size:
            chunks.append("\n\n".join(current))
            # 保留最后一段作为重叠
            overlap_texts = []
            overlap_len = 0
            for t in reversed(current):
                if overlap_len + len(t) + 2 > chunk_overlap:
                    break
                overlap_texts.insert(0, t)
                overlap_len += len(t) + 2
            current = overlap_texts
            current_len = overlap_len

        current.append(para)
        current_len += len(para) + (2 if current_len > 0 else 0)

    if current:
        chunks.append("\n\n".join(current))

    # 构建返回格式
    result = []
    for i, c in enumerate(chunks):
        result.append({
            "chunk_id": f"chunk_{i:06d}",
            "content": c,
            "index": i,
        })
    return result
