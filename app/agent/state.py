from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class WorkerResult(TypedDict, total=False):
    worker: str  # "retrieval" | "code" | "action" | "summary"
    content: str  # Worker 输出内容
    error: str | None  # 错误信息
    metadata: dict  # 额外元数据


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # 对话历史
    worker_assignments: list[str]  # Supervisor 选中的 Worker
    dispatch_reasoning: str  # Supervisor 调度理由
    worker_results: Annotated[list[WorkerResult], operator.add]  # Worker 结果（并行累加）
    refinement_count: int  # 当前反思次数
    refinement_needed: bool  # 是否需要反思重试
    refinement_feedback: str  # Refiner 改进建议
    refinement_targets: list[str]  # 需要重新调度的 Worker
    final_answer: str  # 最终回答
