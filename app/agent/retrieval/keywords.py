from __future__ import annotations

import json

import json_repair

from app.agent.llm.factory import create_llm

KEYWORD_EXTRACTION_PROMPT = """## 角色
你是一个关键词提取助手，负责从用户问题中提取检索关键词。

## 任务
提取两组关键词：
1. **低层级关键词 (ll_keywords)**：用于局部搜索，面向具体实体名称（人名、产品名、项目名等）
2. **高层级关键词 (hl_keywords)**：用于全局搜索，面向关系、概念、主题

## 用户问题
{user_message}

## 输出格式
严格按照以下 JSON 格式输出：
```json
{{
    "ll_keywords": ["关键词1", "关键词2"],
    "hl_keywords": ["概念1", "概念2"]
}}
```
如果问题很短或没有明确的实体，相应数组可以为空。
"""


def extract_keywords(user_message: str) -> dict[str, list[str]]:
    """从用户消息中提取 ll_keywords 和 hl_keywords。"""
    llm = create_llm(temperature=0)
    prompt = KEYWORD_EXTRACTION_PROMPT.replace("{user_message}", user_message)
    response = llm.invoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)

    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        result = json_repair.loads(text)
        return {
            "ll_keywords": result.get("ll_keywords", []),
            "hl_keywords": result.get("hl_keywords", []),
        }
    except Exception:
        return {"ll_keywords": [], "hl_keywords": []}
