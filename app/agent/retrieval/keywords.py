from app.agent.llm import factory as llm_factory
from app.domain.llm_output import KeywordOutput

KEYWORD_EXTRACTION_PROMPT = """## 角色
你是一个关键词提取助手，负责从用户问题中提取检索关键词。

## 任务
提取两组关键词：
1. **低层级关键词 (ll_keywords)**：用于局部搜索，面向具体实体名称（人名、产品名、项目名等）
2. **高层级关键词 (hl_keywords)**：用于全局搜索，面向关系、概念、主题

## 用户问题
{user_message}

如果问题很短或没有明确的实体，相应数组可以为空。
"""


def extract_keywords(user_message: str) -> dict[str, list[str]]:
    """从用户消息中提取 ll_keywords 和 hl_keywords。"""
    llm = llm_factory.create_llm(temperature=0)
    prompt = KEYWORD_EXTRACTION_PROMPT.replace("{user_message}", user_message)

    structured_llm = llm.with_structured_output(KeywordOutput)
    result: KeywordOutput = structured_llm.invoke(prompt)

    return {
        "ll_keywords": result.ll_keywords,
        "hl_keywords": result.hl_keywords,
    }
