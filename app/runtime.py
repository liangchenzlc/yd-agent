from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.agent.eval.eval_manager import EvalManager
from app.agent.graph import build_agent_graph
from app.agent.memory.memory_manager import MemoryManager
from app.agent.storage_manager import StorageManager
from app.config.settings import get_settings


@dataclass
class RuntimeContext:
    storage_manager: StorageManager
    memory_manager: MemoryManager
    eval_manager: EvalManager
    graph: object


class AgentRuntime:
    async def __aenter__(self) -> RuntimeContext:
        settings = get_settings()
        storage_manager = StorageManager(storage_dir=settings.storage_dir)
        await storage_manager.initialize()

        memory_manager = MemoryManager(storage_dir=settings.storage_dir)
        await memory_manager.initialize()

        eval_manager = EvalManager(storage_dir=settings.storage_dir)
        await eval_manager.initialize()

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
        await self.context.eval_manager.finalize()
        await self.context.storage_manager.finalize()
        await self.context.memory_manager.finalize()
        return False
