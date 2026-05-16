"""共享测试辅助函数（无 mock，全真实依赖）。"""

from langchain_core.messages import HumanMessage

from app.agent.state import AgentState


def make_initial_state(message: str, user_id: str = "default") -> AgentState:
    """创建一个初始 AgentState 用于测试。"""
    return AgentState(
        messages=[HumanMessage(content=message)],
        worker_assignments=[],
        dispatch_reasoning="",
        worker_results=[],
        refinement_count=0,
        refinement_needed=False,
        refinement_feedback="",
        refinement_targets=[],
        final_answer="",
        user_id=user_id,
        session_id="test",
        user_profile={},
        relevant_memories=[],
        session_history=[],
    )
