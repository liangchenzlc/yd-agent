from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from app.agent.eval.eval_manager import EvalManager
from app.agent.graph import build_agent_graph
from app.agent.memory.memory_manager import MemoryManager
from app.agent.storage_manager import StorageManager
from app.config.settings import get_settings


@dataclass
class RuntimeContext:
    """Agent 运行上下文：聚合所有管理器实例和编译后的 Graph。

    作为 __aenter__ 的返回值，让调用方通过一个对象访问所有资源。
    """
    storage_manager: StorageManager
    memory_manager: MemoryManager
    eval_manager: EvalManager
    graph: object


class AgentRuntime:
    """异步上下文管理器，每个 tenant 一个实例，负责 Agent 生命周期内的资源初始化和清理。

    通过 __aenter__ / __aexit__ 确保 StorageManager（FAISS/BM25/KV）、MemoryManager、EvalManager
    正确初始化并在退出时持久化，避免资源泄漏。
    """

    def __init__(self, tenant_id: str = "default"):
        self._tenant_id = tenant_id

    async def __aenter__(self) -> RuntimeContext:
        settings = get_settings()
        # 每个 tenant 的数据隔离在独立子目录下，防止不同租户的向量索引/记忆互相污染
        tenant_dir = str(Path(settings.storage_dir) / self._tenant_id)

        # get_cached 返回单例缓存 —— 同一 tenant_dir 的 FAISS 索引和 BM25 倒排表只加载一次，
        # 避免在同一进程中重复构建的开销（P0 性能优化）。缓存超过 MAX_CACHED_INSTANCES 时自动驱逐最旧实例。
        storage_manager = StorageManager.get_cached(tenant_dir)

        # MemoryManager 不缓存，因为每次会话的记忆上下文不同，需要重新从 KV 存储中加载
        memory_manager = MemoryManager(tenant_id=self._tenant_id)
        memory_manager.initialize()

        eval_manager = EvalManager(tenant_id=self._tenant_id)
        eval_manager.initialize()

        # 注入 storage_manager / memory_manager 到 Agent Graph 节点，
        # 使得 retrieval_worker 和 load_memory / save_memory 节点能访问持久化层
        graph = build_agent_graph(
            storage_manager=storage_manager,
            memory_manager=memory_manager,
        )
        self.context = RuntimeContext(
            storage_manager=storage_manager,
            memory_manager=memory_manager,
            eval_manager=eval_manager,
            graph=graph,
        )
        return self.context

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        # 持久化顺序：eval → storage → memory。
        # eval_manager 可能依赖 storage_manager 做持久化，
        # memory_manager 放在最后确保前面所有状态都已落盘
        self.context.eval_manager.finalize()
        self.context.storage_manager.finalize()
        self.context.memory_manager.finalize()
        return False
