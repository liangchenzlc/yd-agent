from __future__ import annotations

import math
import re
from typing import Any

# 递归分隔符列表：按优先级递减排列，保证切分时不会在句子中间截断。
# "" 作为兜底分隔符，当所有语义分隔符都找不到时按字符切分。
SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", " ", ""]

# 标题检测模式列表，按常见文档格式覆盖：
# 1. Markdown 标题（# ## ###）
# 2. 中文"第X章/节/条"（法律文书、技术文档常见格式）
# 3. 数字编号标题（1. 2. 3.）
# 4. 子标题（1.1 2.3）
# 5. 带括号的编号标题（(1)（2））
# 6. 中文【标题】（公文、公告常用）
# level 用于标题栈的管理：level=1 替换当前层级，level=2 追加为子层级
HEADER_PATTERNS: list[tuple[int, re.Pattern]] = [
    (1, re.compile(r"^#{1,3}\s+(.+)$")),                          # ## Markdown 标题
    (1, re.compile(r"^第[一二三四五六七八九十百\d]+[章节条]\s*(.*)$")),  # 第X章/节/条
    (1, re.compile(r"^\d+\.\s+(.+)$")),                            # 1. 数字标题
    (2, re.compile(r"^\d+\.\d+\s+(.+)$")),                        # 1.1 子标题
    (2, re.compile(r"^[\(（]\d+[\)）]\s*(.+)$")),                   # (1) 编号标题
    (1, re.compile(r"^【(.+)】$")),                                 # 【标题】
]


def _detect_header(line: str) -> tuple[str | None, int]:
    """检测行是否为标题。

    Returns:
        (header_text, level) 或 (None, 0)。
    """
    stripped = line.strip()
    if not stripped:
        return None, 0
    for level, pattern in HEADER_PATTERNS:
        m = pattern.match(stripped)
        if m:
            return m.group(1).strip() or stripped, level
    return None, 0


def _find_split_pos(text: str, max_pos: int) -> int:
    """在 max_pos 之前找到最合适的切分位置。

    搜索优先级：句号类（句子边界）> 逗号（短语边界）> 空格（单词边界）> 直接切。
    search_start 设为 max(一半位置, max_pos-100) 的原因：
    当 max_pos 较小时（如短段落），从一半位置开始搜避免搜到太靠前的位置；
    当 max_pos 较大时，限制搜索窗口到 100 字符以提高性能。
    """
    if max_pos >= len(text):
        return len(text)

    # 在 max_pos 附近找句号类分隔符
    search_start = max(max_pos // 2, max_pos - 100)
    search_end = max_pos

    for sep in ["。", "！", "？", "\n", "；"]:
        pos = text.rfind(sep, search_start, search_end)
        if pos != -1:
            return pos + len(sep)

    # 回退到逗号
    pos = text.rfind("，", search_start, search_end)
    if pos != -1:
        return pos + 1

    # 回退到空格
    pos = text.rfind(" ", search_start, search_end)
    if pos != -1:
        return pos + 1

    return max_pos


def chunk_text(
    text: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> list[dict[str, Any]]:
    """递归分块 + 文档结构感知。

    使用多级分隔符递归切分，检测标题结构并记录 header_path，
    长段落按句子边界切分而非固定窗口。

    Args:
        text: 输入文本。
        chunk_size: 每块最大字符数。
        chunk_overlap: 块间重叠字符数。

    Returns:
        [{chunk_id, content, index, metadata}, ...]
    """
    if not text.strip():
        return []

    # 先用双换行切分为段落，这是最高优先级的语义分割点
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    headers: list[str] = []  # 当前标题路径栈，用于构建 header_path
    metadata_list: list[dict[str, Any]] = []

    current: list[str] = []
    current_len = 0
    current_headers = list(headers)  # 当前累积块的标题上下文

    def _flush():
        """将 current 中的段落合并为一个 chunk 写入。

        写入后保留尾部部分段落作为下一 chunk 的重叠内容，
        确保跨 chunk 的语义连续性（尤其当标题分割块时）。
        """
        nonlocal current, current_len
        if not current:
            return
        joined = "\n\n".join(current)
        chunks.append(joined)
        metadata_list.append({
            "header_path": " > ".join(current_headers) if current_headers else "",
            "header_level": len(current_headers),
            "chunk_size_chars": len(joined),
            "estimated_tokens": _estimate_tokens(joined),
        })
        # 保留尾部内容做重叠
        overlap_texts = []
        overlap_len = 0
        for t in reversed(current):
            t_len = len(t) + 2
            if overlap_len + t_len > chunk_overlap:
                break
            overlap_texts.insert(0, t)
            overlap_len += t_len
        current = overlap_texts
        current_len = overlap_len

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # 检测标题，先保存更新前的标题栈状态
        # 设计约束：标题处理必须在 flush 决策之前，
        # 因为 flush 时需要知道 flush 的内容属于哪个标题上下文
        first_line = para.split("\n")[0] if para else ""
        header_text, header_level = _detect_header(first_line)
        headers_before = list(headers)

        if header_text is not None:
            if header_level <= len(headers):
                headers = headers[: header_level - 1]
            headers.append(header_text)

        # 如果单一段落超过 chunk_size，需要直接切分
        if len(para) > chunk_size:
            _flush()
            # 该段落内含标题，后续块携带更新后的标题栈
            para_headers = list(headers)
            pos = 0
            while pos < len(para):
                end = _find_split_pos(para, pos + chunk_size)
                if end <= pos:
                    end = min(pos + chunk_size, len(para))
                chunk_text_content = para[pos:end].strip()
                if chunk_text_content:
                    chunks.append(chunk_text_content)
                    metadata_list.append({
                        "header_path": " > ".join(para_headers) if para_headers else "",
                        "header_level": len(para_headers),
                        "chunk_size_chars": len(chunk_text_content),
                        "estimated_tokens": _estimate_tokens(chunk_text_content),
                    })
                pos = end - chunk_overlap if end < len(para) else len(para)
            # 重叠后重置 current_headers（后续段落携带新标题）
            current_headers = list(headers)
            continue

        # 超过 chunk_size，先 flush
        # 此时 flush 的块应使用 headers_before（即将加入的标题属于下一块）
        if current_len + len(para) + 2 > chunk_size:
            current_headers = headers_before
            _flush()

        current.append(para)
        current_len += len(para) + (2 if current_len > 0 else 0)
        # 更新 current_headers 以反映新追加段落的标题上下文
        current_headers = list(headers)

    if current:
        current_headers = list(headers)  # 最后一块携带最新标题
        _flush()

    # 构建返回格式
    result = []
    for i, (c, meta) in enumerate(zip(chunks, metadata_list)):
        result.append({
            "chunk_id": f"chunk_{i:06d}",
            "content": c,
            "index": i,
            "metadata": meta,
        })
    return result


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文字符按 1.5 tokens，英文按 1 token。

    注意：这不是精确的 token 计数，只是用于 chunk_size 的粗略估算。
    实际 LLM 的 tokenizer（如 cl100k_base）对中英文的编码更复杂，
    但这个估算对分块策略已经足够——我们只需要确保 chunk 不会过度超过模型上下文限制。
    """
    chinese_chars = len(re.findall(r"[一-鿿]", text))
    other_chars = len(text) - chinese_chars
    return math.ceil(chinese_chars * 1.5 + other_chars * 0.4)
