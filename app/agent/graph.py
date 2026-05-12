from functools import partial

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from app.agent.state import AgentState
from app.agent.nodes.supervisor import supervisor_node
from app.agent.nodes.retrieval_worker import retrieval_worker_node
from app.agent.nodes.code_worker import code_worker_node
from app.agent.nodes.docs_worker import docs_worker_node
from app.agent.nodes.summary_worker import summary_worker_node
from app.agent.nodes.refiner import refiner_node
from app.agent.nodes.load_memory import load_memory_node
from app.agent.nodes.save_memory import save_memory_node
from app.agent.storage_manager import StorageManager
from app.agent.memory.memory_manager import MemoryManager
from app.agent.tools import ToolRegistry

# Worker 名称 → 图节点名称 映射
WORKER_NODE_MAP = {
    "retrieval": "retrieval_worker",
    "code": "code_worker",
    "docs": "docs_worker",
    "summary": "summary_worker",
}


def route_to_workers(state: AgentState) -> list[Send]:
    """Supervisor 之后的条件路由：根据 worker_assignments 并行分发。"""
    assignments = state.get("refinement_targets") or state.get("worker_assignments", [])
    if not assignments:
        assignments = ["summary"]
    return [Send(WORKER_NODE_MAP[w], state) for w in assignments if w in WORKER_NODE_MAP]


def route_after_refiner(state: AgentState):
    """Refiner 之后的条件路由：决定重试还是保存记忆并结束。"""
    if state.get("refinement_needed") and state.get("refinement_count", 0) < 2:
        return "supervisor"
    return "save_memory"


def build_agent_graph(
    storage_manager: StorageManager | None = None,
    memory_manager: MemoryManager | None = None,
):
    """构建并编译多智能体 StateGraph。

    Args:
        storage_manager: 可选的存储管理器实例，用于 GraphRAG 检索。
        memory_manager: 可选的记忆管理器实例，用于用户记忆的加载和存储。
    """
    # 初始化工具注册表
    ToolRegistry.init_defaults()

    builder = StateGraph(AgentState)

    # 注册所有节点
    builder.add_node("load_memory", partial(load_memory_node, memory_manager=memory_manager))
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("retrieval_worker", partial(retrieval_worker_node, storage_manager=storage_manager))
    builder.add_node("code_worker", code_worker_node)
    builder.add_node("docs_worker", docs_worker_node)
    builder.add_node("summary_worker", summary_worker_node)
    builder.add_node("refiner", refiner_node)
    builder.add_node("save_memory", partial(save_memory_node, memory_manager=memory_manager))

    # 入口：先加载记忆
    builder.set_entry_point("load_memory")
    builder.add_edge("load_memory", "supervisor")

    # Supervisor → 并行分发 Worker
    builder.add_conditional_edges("supervisor", route_to_workers)

    # 所有 Worker → 汇总 Worker
    builder.add_edge("retrieval_worker", "summary_worker")
    builder.add_edge("code_worker", "summary_worker")
    builder.add_edge("docs_worker", "summary_worker")
    builder.add_edge("summary_worker", "refiner")

    # Refiner → 条件路由（重试或保存记忆）
    builder.add_conditional_edges("refiner", route_after_refiner)
    builder.add_edge("save_memory", END)

    # 编译
    return builder.compile()
