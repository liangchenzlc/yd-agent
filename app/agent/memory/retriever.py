from __future__ import annotations


def format_memory_context(memories: list[dict]) -> str:
    """将记忆列表格式化为 prompt 可用的上下文文本。"""
    if not memories:
        return "（暂无相关历史记忆）"

    lines = []
    for m in memories:
        text = m.get("text", m.get("content", ""))
        meta = m.get("metadata", {})
        mem_type = meta.get("type", m.get("type", ""))
        importance = meta.get("importance", m.get("importance", 0))
        if mem_type:
            lines.append(f"- [{mem_type}](重要度:{importance:.1f}) {text}")
        else:
            lines.append(f"- {text}")

    return "\n".join(lines)


def format_profile_context(profile: dict) -> str:
    """将用户画像格式化为 prompt 可用的上下文文本。"""
    if not profile or not profile.get("topics") and not profile.get("recent_history"):
        return "（新用户，暂无画像信息）"

    lines = []
    topics = profile.get("topics", {})
    if topics:
        top_topics = sorted(topics.items(), key=lambda kv: kv[1], reverse=True)[:5]
        lines.append(f"常用话题：{', '.join(t[0] for t in top_topics)}")

    total = profile.get("total_interactions", 0)
    lines.append(f"已交互 {total} 次")

    return "\n".join(lines)
