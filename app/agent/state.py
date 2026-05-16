from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class WorkerResult(TypedDict, total=False):
    """Worker 节点输出结果。

    total=False 表示非所有字段都必须填充：出错时可能只有 worker + error 两个字段。
    metadata 用于传递辅助信息（如 low_confidence、refinement_count），
    supervisor 和 refiner 节点通过它做路由决策。
    """
    worker: str
    content: str
    error: str | None
    metadata: dict


class AgentState(TypedDict):
    """LangGraph 状态定义：贯穿整个 Agent 生命周期的共享状态容器。

    Annotated[T, reducer] 是 LangGraph 的状态更新机制：
    多个并行节点同时写入同一字段时，通过 reducer 函数合并而非覆盖。
    这是 LangGraph 并行调度的核心契约——不使用 reducer 的字段会互相覆盖。
    """
    # add_messages reducer：并行节点追加消息时自动合并为列表，而非覆盖
    messages: Annotated[list[BaseMessage], add_messages]

    # Supervisor 根据用户问题动态选中的 Worker 列表（如 ["retrieval", "data_analyst"]）
    worker_assignments: list[str]
    dispatch_reasoning: str

    # operator.add reducer：多个并行 Worker 各自 append 自己的 WorkerResult，
    # refiner 和 summary_worker 读取整个列表做聚合分析
    worker_results: Annotated[list[WorkerResult], operator.add]

    refinement_count: int
    refinement_needed: bool
    refinement_feedback: str
    refinement_targets: list[str]
    final_answer: str

    user_id: str
    session_id: str
    # load_memory 节点填充，供所有下游节点参考
    user_profile: dict
    relevant_memories: list[dict]
    session_history: list[dict]


class DocumentItem(TypedDict, total=False):
    id: str
    content: str
    metadata: dict


class IngestionState(TypedDict):
    """文档摄入流程的 Graph 状态。

    current_index 驱动遍历：mark_completed 节点自增，should_continue 判断是否结束。
    is_duplicate 被 check_duplicates 设为 True 时，chunk/embed/save 全部跳过。
    """
    documents: list[DocumentItem]
    current_index: int
    doc_id: str
    content: str
    metadata: dict
    is_duplicate: bool
    chunks: list[dict]
    total_ingested: int
    total_skipped: int
    total_chunks: int
    error: str | None
