from langgraph.graph import StateGraph, END
from langgraph.types import Send

from app.agent.state import AgentState
from app.agent.nodes.supervisor import supervisor_node
from app.agent.nodes.retrieval_worker import retrieval_worker_node
from app.agent.nodes.code_worker import code_worker_node
from app.agent.nodes.action_worker import action_worker_node
from app.agent.nodes.summary_worker import summary_worker_node
from app.agent.nodes.refiner import refiner_node

# Worker 名称 → 图节点名称 映射
WORKER_NODE_MAP = {
    "retrieval": "retrieval_worker",
    "code": "code_worker",
    "action": "action_worker",
    "summary": "summary_worker",
}


def route_to_workers(state: AgentState) -> list[Send]:
    """Supervisor 之后的条件路由：根据 worker_assignments 并行分发。"""
    assignments = state.get("worker_assignments", [])
    if not assignments:
        assignments = ["summary"]
    return [Send(WORKER_NODE_MAP[w], state) for w in assignments if w in WORKER_NODE_MAP]


def route_after_refiner(state: AgentState):
    """Refiner 之后的条件路由：决定重试还是结束。"""
    if state.get("refinement_needed") and state.get("refinement_count", 0) < 2:
        return "supervisor"
    return END


def build_agent_graph():
    """构建并编译多智能体 StateGraph。"""
    builder = StateGraph(AgentState)

    # 注册所有节点
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("retrieval_worker", retrieval_worker_node)
    builder.add_node("code_worker", code_worker_node)
    builder.add_node("action_worker", action_worker_node)
    builder.add_node("summary_worker", summary_worker_node)
    builder.add_node("refiner", refiner_node)

    # 入口
    builder.set_entry_point("supervisor")

    # Supervisor → 并行分发 Worker
    builder.add_conditional_edges("supervisor", route_to_workers)

    # 所有 Worker → 汇总 Worker
    builder.add_edge("retrieval_worker", "summary_worker")
    builder.add_edge("code_worker", "summary_worker")
    builder.add_edge("action_worker", "summary_worker")
    builder.add_edge("summary_worker", "refiner")

    # Refiner → 条件路由
    builder.add_conditional_edges("refiner", route_after_refiner)

    # 编译
    return builder.compile()
