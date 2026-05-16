from functools import partial

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from app.agent.state import AgentState
from app.agent.nodes.supervisor import supervisor_node
from app.agent.nodes.retrieval_worker import retrieval_worker_node
from app.agent.nodes.docs_worker import docs_worker_node
from app.agent.nodes.summary_worker import summary_worker_node
from app.agent.nodes.refiner import refiner_node
from app.agent.nodes.load_memory import load_memory_node
from app.agent.nodes.data_analyst_worker import data_analyst_worker_node
from app.agent.nodes.save_memory import save_memory_node
from app.agent.constants import MAX_REFINEMENTS
from app.agent.storage_manager import StorageManager
from app.agent.memory.memory_manager import MemoryManager

# Worker 名称 → 图节点名称 映射
# 该映射将 Supervisor 输出的逻辑 Worker 名（如 "retrieval"）转换为
# StateGraph 中注册的节点名（如 "retrieval_worker"）
WORKER_NODE_MAP = {
    "retrieval": "retrieval_worker",
    "docs": "docs_worker",
    "data_analyst": "data_analyst_worker",
    "summary": "summary_worker",
}


def route_to_workers(state: AgentState) -> list[Send]:
    """Supervisor 之后的条件路由：根据 worker_assignments 并行分发。

    Fan-out 机制：使用 LangGraph Send() 将 Supervisor 的决策分发到多个 Worker 节点并行执行。
    Send() 的第二个参数传入 state 的完整副本，这是 LangGraph 的 API 约束——每个 Send 代表一条独立的执行路径。

    优先级：refinement_targets（Refiner 指定的重试目标）> worker_assignments（Supervisor 的原始分配）> summary（兜底）。
    """
    assignments = state.get("refinement_targets") or state.get("worker_assignments", [])
    if not assignments:
        assignments = ["summary"]
    # 过滤非法 Worker 名，防止 Send 到不存在的节点导致运行时崩溃
    return [Send(WORKER_NODE_MAP[w], state) for w in assignments if w in WORKER_NODE_MAP]


def route_after_summary(state: AgentState) -> str:
    """Summary 之后的路由：低置信度时走 Refiner，否则直接保存记忆。

    置信度由各 Worker 的 metadata.low_confidence 标记，任何 Worker 报告低置信度都触发反思。
    注意：只检查当前轮次的 worker_results，避免旧轮次残留的 low_confidence 触发无谓重试。
    因为 supervisor 返回 worker_results=[] 无法清除 operator.add 已积累的历史结果。
    """
    current_round = state.get("refinement_count", 0)
    worker_results = state.get("worker_results", [])
    # 只筛选当前轮次的结果（与 refiner_node 的过滤逻辑一致）
    current_results = [
        r for r in worker_results
        if r.get("metadata", {}).get("refinement_count", 0) == current_round
    ]
    has_low_confidence = any(
        r.get("metadata", {}).get("low_confidence")
        for r in current_results
    )
    if has_low_confidence:
        return "refiner"
    return "save_memory"


def route_after_refiner(state: AgentState):
    """Refiner 之后的路由：决定重试还是保存记忆。

    refinement_count >= MAX_REFINEMENTS（默认 3）时强制结束，防止无限循环。
    这是兜底保护而非质量决策——即使 LLM 认为还需要改进也停止。
    """
    if state.get("refinement_needed") and state.get("refinement_count", 0) < MAX_REFINEMENTS:
        return "supervisor"
    return "save_memory"


def build_agent_graph(
    storage_manager: StorageManager | None = None,
    memory_manager: MemoryManager | None = None,
):
    """构建并编译多智能体 StateGraph。

    架构：load_memory → supervisor → [并行 Worker] → summary_worker → {refiner | save_memory}
    StorageManager 和 MemoryManager 通过 partial 注入，无需全局变量或 DI 框架。
    """
    builder = StateGraph(AgentState)

    # 注册所有节点。partial 将外部依赖（storage/memory）注入到节点函数，
    # 保持节点函数签名不被外部依赖污染
    builder.add_node("load_memory", partial(load_memory_node, memory_manager=memory_manager))
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("retrieval_worker", partial(retrieval_worker_node, storage_manager=storage_manager))
    builder.add_node("docs_worker", docs_worker_node)
    builder.add_node("summary_worker", summary_worker_node)
    builder.add_node("data_analyst_worker", data_analyst_worker_node)
    builder.add_node("refiner", refiner_node)
    builder.add_node("save_memory", partial(save_memory_node, memory_manager=memory_manager))

    # 入口：load_memory → supervisor
    builder.set_entry_point("load_memory")
    builder.add_edge("load_memory", "supervisor")

    # Supervisor → [并行 Worker]：Send() 实现动态 Fan-out
    builder.add_conditional_edges("supervisor", route_to_workers)

    # [Worker] → summary_worker：LangGraph 的 Fan-in 同步屏障
    builder.add_edge("retrieval_worker", "summary_worker")
    builder.add_edge("docs_worker", "summary_worker")
    builder.add_edge("data_analyst_worker", "summary_worker")

    # Summary → {Refiner | Save}：低置信度条件路由
    builder.add_conditional_edges(
        "summary_worker",
        route_after_summary,
        {"refiner": "refiner", "save_memory": "save_memory"},
    )

    # Refiner → {Supervisor | Save}：重试或结束
    builder.add_conditional_edges("refiner", route_after_refiner)
    builder.add_edge("save_memory", END)

    return builder.compile()
