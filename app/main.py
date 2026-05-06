from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes import health, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：预构建图实例
    chat.get_graph()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="yd-Agent",
        description="企业级 AI 助手系统 — 多智能体编排",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router, tags=["health"])
    app.include_router(chat.router, tags=["chat"])
    return app


app = create_app()
