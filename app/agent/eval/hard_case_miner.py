from __future__ import annotations

from app.agent.llm import factory as llm_factory
from app.agent.prompts import GOLDEN_ANSWER_PROMPT


async def generate_golden_answer(
    user_message: str,
    original_answer: str,
    worker_results: list[dict],
    golden_model: str | None = None,
) -> str:
    """为低质量回答生成金标答案。

    如果 golden_model 为空，则跳过生成，返回空字符串。
    """
    if not golden_model:
        return ""

    # 格式化 Worker 结果（截断防止 token 超限）
    if worker_results:
        lines = []
        for r in worker_results:
            w = r.get("worker", "unknown")
            c = r.get("content", "")
            e = r.get("error")
            status = "失败" if e else "成功"
            truncated = c[:1000] + ("..." if len(c) > 1000 else "")
            lines.append(f"### {w} ({status})\n{truncated}")
        worker_results_text = "\n\n".join(lines)
    else:
        worker_results_text = "[无 Worker 执行结果]"

    prompt = (
        GOLDEN_ANSWER_PROMPT.replace("{user_message}", user_message)
        .replace("{original_answer}", original_answer)
        .replace("{worker_results}", worker_results_text)
    )

    try:
        llm = llm_factory.create_llm(temperature=0, model=golden_model)
        response = await llm.ainvoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception:
        return ""
