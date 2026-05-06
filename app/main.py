from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI

from app.api.routes import health, chat, documents, memory, eval as eval_routes
from app.agent.storage_manager import StorageManager
from app.agent.memory.memory_manager import MemoryManager
from app.agent.eval.eval_manager import EvalManager
from app.agent.eval.maintenance import schedule_eval_maintenance
from app.agent.constants import EVAL_MAX_RECENT_RUNS
from app.config.settings import get_settings

_storage_manager: StorageManager | None = None
_memory_manager: MemoryManager | None = None
_eval_manager: EvalManager | None = None


def get_storage_manager() -> StorageManager | None:
    return _storage_manager


def get_memory_manager() -> MemoryManager | None:
    return _memory_manager


def get_eval_manager() -> EvalManager | None:
    return _eval_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _storage_manager, _memory_manager, _eval_manager
    settings = get_settings()

    # 初始化存储管理器
    mgr = StorageManager(storage_dir=settings.storage_dir)
    await mgr.initialize()
    _storage_manager = mgr

    # 初始化记忆管理器
    mem_mgr = MemoryManager(storage_dir=settings.storage_dir)
    await mem_mgr.initialize()
    _memory_manager = mem_mgr

    # 初始化评估管理器
    eval_mgr = EvalManager(storage_dir=settings.storage_dir)
    await eval_mgr.initialize()
    _eval_manager = eval_mgr

    # 预构建图实例，传入 storage_manager 和 memory_manager
    chat.get_graph(storage_manager=mgr, memory_manager=mem_mgr)

    # 启动后台评估维护任务
    maint_task = None
    if settings.eval_enabled:
        maint_task = asyncio.create_task(
            schedule_eval_maintenance(
                eval_manager=eval_mgr,
                interval_hours=settings.eval_maintenance_interval_hours,
                retention_days=settings.eval_retention_days,
                max_runs=EVAL_MAX_RECENT_RUNS,
            )
        )

    yield

    # 取消后台维护任务
    if maint_task:
        maint_task.cancel()
        try:
            await maint_task
        except asyncio.CancelledError:
            pass

    # 关闭时持久化
    if _eval_manager:
        await _eval_manager.finalize()
    if _storage_manager:
        await _storage_manager.finalize()
    if _memory_manager:
        await _memory_manager.finalize()


def create_app() -> FastAPI:
    app = FastAPI(
        title="yd-Agent",
        description="企业级 AI 助手系统 — 多智能体编排 + GraphRAG 增强检索",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.include_router(health.router, tags=["health"])
    app.include_router(chat.router, tags=["chat"])
    app.include_router(documents.router, tags=["documents"])
    app.include_router(memory.router, tags=["memory"])
    app.include_router(eval_routes.router, tags=["eval"])
    return app


app = create_app()
