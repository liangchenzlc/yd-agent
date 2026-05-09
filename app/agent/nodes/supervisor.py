from app.agent.state import AgentState
from app.agent.prompts import SUPERVISOR_PROMPT
from app.agent.llm import factory as llm_factory
from app.agent.constants import ALL_WORKERS
from app.agent.memory.retriever import format_profile_context
from app.domain.llm_output import SupervisorOutput


def supervisor_node(state: AgentState) -> dict:
    """Supervisor 节点：分析用户意图，决定调度哪些 Worker。"""
    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    user_profile_section = format_profile_context(state.get("user_profile", {}))
    prompt = (
        SUPERVISOR_PROMPT.replace("{user_profile_section}", user_profile_section)
        .replace("{user_message}", user_message)
    )

    try:
        structured_llm = llm.with_structured_output(SupervisorOutput)
        result: SupervisorOutput = structured_llm.invoke(prompt)
        workers = [w for w in result.workers if w in ALL_WORKERS]
        reasoning = result.reasoning
    except Exception:
        workers = []
        reasoning = ""

    if not workers:
        workers = ["summary"]

    return {
        "worker_assignments": workers,
        "dispatch_reasoning": reasoning,
        "worker_results": [],
    }
