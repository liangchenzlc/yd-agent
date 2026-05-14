from app.agent.state import AgentState
from app.agent.llm import factory as llm_factory
from app.agent.constants import ALL_WORKERS
from app.agent.conversation import format_conversation_context
from app.agent.memory.retriever import format_profile_context
from app.agent.prompts import SUPERVISOR_PROMPT, fill_prompt
from app.domain.llm_output import SupervisorOutput


def supervisor_node(state: AgentState) -> dict:
    """Supervisor 节点：分析用户意图，决定调度哪些 Worker。"""
    refinement_targets = state.get("refinement_targets", [])
    if refinement_targets:
        return {
            "worker_assignments": [w for w in refinement_targets if w in ALL_WORKERS] or ["summary"],
            "dispatch_reasoning": state.get("refinement_feedback", ""),
            "worker_results": [],
            "refinement_targets": [],
        }

    llm = llm_factory.create_llm()
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    user_profile_section = format_profile_context(state.get("user_profile", {}))
    prompt = fill_prompt(SUPERVISOR_PROMPT,
        user_profile_section=user_profile_section,
        user_message=user_message,
        conversation_context=format_conversation_context(messages),
    )

    try:
        from json_repair import loads

        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        decoded_result = loads(content)
        result = SupervisorOutput.model_validate(decoded_result)
        workers = [w for w in result.workers if w in ALL_WORKERS]
        reasoning = result.reasoning
    except (ValueError, TypeError, KeyError):
        workers = []
        reasoning = ""

    if not workers:
        workers = ["summary"]

    return {
        "worker_assignments": workers,
        "dispatch_reasoning": reasoning,
        "worker_results": [],
    }
