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

    user_id: str  # 用户标识
    session_id: str  # 会话标识
    user_profile: dict  # 用户画像（load_memory 后填充）
    relevant_memories: list[dict]  # 相关历史记忆
    session_history: list[dict]  # 近期会话历史


class DocumentItem(TypedDict, total=False):
    id: str
    content: str
    metadata: dict


class IngestionState(TypedDict):
    documents: list[DocumentItem]  # 待处理的原始文档
    current_index: int  # 当前处理的文档索引
    doc_id: str  # 当前文档 ID
    content: str  # 当前文档内容
    metadata: dict  # 当前文档元数据
    is_duplicate: bool  # 是否为重复文档
    chunks: list[dict]  # 分块结果
    entities: list[dict]  # 抽取的实体
    relationships: list[dict]  # 抽取的关系
    total_ingested: int  # 已摄入文档数
    total_skipped: int  # 跳过的文档数
    total_chunks: int  # 总块数
    total_entities: int  # 总实体数
    total_relationships: int  # 总关系数
    error: str | None  # 错误信息
