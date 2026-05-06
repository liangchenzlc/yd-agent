from app.agent.state import AgentState
from app.agent.prompts import SUMMARY_PROMPT
from app.agent.llm import factory as llm_factory


def summary_worker_node(state: AgentState) -> dict:
    """汇总 Worker：聚合所有 Worker 结果，生成最终回答。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    worker_results = state.get("worker_results", [])

    # 格式化 Worker 结果
    if worker_results:
        lines = []
        for r in worker_results:
            w = r.get("worker", "unknown")
            c = r.get("content", "")
            e = r.get("error")
            status = "失败" if e else "成功"
            lines.append(f"### {w} ({status})\n{c}")
        results_text = "\n\n".join(lines)
    else:
        results_text = "[无 Worker 执行结果，请直接回答用户问题]"

    prompt = SUMMARY_PROMPT.replace("{user_message}", user_message).replace("{worker_results}", results_text)
    response = llm.invoke(prompt)
    final_answer = response.content if hasattr(response, "content") else str(response)

    return {"final_answer": final_answer}
