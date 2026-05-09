from app.agent.llm import factory as llm_factory
from app.domain.llm_output import MemoryExtractionOutput

MEMORY_EXTRACTION_PROMPT = """## 角色
你是一个信息提取助手，负责从对话中提取需要长期记住的信息，用于构建用户画像和跨会话记忆。

## 提取类型
- **fact**: 用户事实——角色、专业领域、个人信息（如"我是后端工程师"）
- **preference**: 偏好——喜欢的格式、语气、风格（如"我喜欢简洁的回答"）
- **pattern**: 行为模式——反复出现的需求模式（如"用户经常问周报模板"）
- **template**: 可复用模板——用户接受并想复用的输出格式

## 用户消息
{user_message}

## 系统回答
{final_answer}

## 规则
1. 只提取需要长期记忆的重要信息，忽略闲聊。
2. importance 分数 0-1：1.0 = 必须记住，0.0 = 可忽略。
3. 如果对话中没有值得长期记忆的信息，返回空数组。
4. 每个记忆不超过一句话。

## 输出格式
请以 JSON 格式输出。
"""


def extract_memories_from_conversation(
    user_message: str,
    final_answer: str,
) -> list[dict]:
    """从对话中提取结构化记忆。"""
    llm = llm_factory.create_llm(temperature=0)
    prompt = (
        MEMORY_EXTRACTION_PROMPT.replace("{user_message}", user_message)
        .replace("{final_answer}", final_answer)
    )

    structured_llm = llm.with_structured_output(MemoryExtractionOutput)
    result: MemoryExtractionOutput = structured_llm.invoke(prompt)

    return [
        {"type": m.type, "content": m.content, "importance": m.importance, "category": m.category}
        for m in result.memories
        if m.content
    ]
