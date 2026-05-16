from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from time import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.user import router as user_router
from app.config.logging import setup_logging
from app.config.settings import get_settings
from app.web.auth import decode_token, ensure_default_admin, _secret
from app.web.db import db
from app.agent.storage.redis_cache import redis_cache
from app.agent.tools import ToolRegistry
from app.agent.stats.usage_tracker import track_api_call

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """FastAPI 生命周期：启动时初始化全局资源，关闭时清理。

    初始化顺序有依赖关系：
    1. 日志（必须最先，否则后续日志无法记录）
    2. Secret Key 校验（没有密钥则直接启动失败，避免运行时才发现）
    3. 数据库（用于用户认证和文档记录）
    4. Redis 缓存（用量统计依赖）
    5. 默认管理员（依赖数据库）
    6. 工具注册（依赖配置，只需初始化一次）

    ToolRegistry.init_defaults() 在 lifespan 中调用而非在每个请求中，
    因为工具实例的创建涉及反射和 Pydantic model 构建，开销不可忽略。
    只需在服务器启动时初始化一次，后续所有请求共享同一批工具实例。
    """
    setup_logging("data/logs")
    _secret()
    logger.info("Starting yd-Agent server")
    db.initialize()
    redis_cache.initialize()
    ensure_default_admin()
    ToolRegistry.init_defaults()
    logger.info("Server initialization complete")
    yield
    redis_cache.close()
    logger.info("Server shutdown")


app = FastAPI(title="yd-Agent Enterprise Knowledge Desk", version="0.1.0", lifespan=lifespan)

# CORS 配置：仅允许本地开发用的 Vite 前端端口，
# 生产环境应替换为实际前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router)
app.include_router(admin_router)


def _extract_user_info(request: Request) -> tuple[int, str]:
    """从请求中提取用户 ID 和 tenant_id：优先 Bearer Token，其次 Cookie。

    用于用量统计中间件中标记每次 API 调用的用户及其所属租户。
    如果解析失败（token 过期、无效等），返回 (0, "default") 而非抛出异常，
    因为统计中间件不应因认证问题而阻断请求链。
    """
    token_str = ""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token_str = auth.split(" ", 1)[1]
    else:
        token_str = request.cookies.get("access_token", "")
    if not token_str:
        return 0, "default"
    try:
        payload = decode_token(token_str)
        return int(payload.get("sub", 0)), payload.get("tenant_id", "default")
    except Exception:
        logger.warning("Failed to extract user info from token", exc_info=True)
        return 0, "default"


@app.middleware("http")
async def usage_stats_middleware(request: Request, call_next):
    """用量统计中间件：记录每个 API 请求的路径和耗时。

    排除非 API 路径（静态文件等）和登录接口（避免统计噪音）。
    在响应头中添加 X-Response-Time-Ms 便于前端排查性能问题。
    统计追踪失败时仅记录 warning 日志，不阻塞请求处理。
    """
    path = request.url.path
    if not path.startswith("/api/") or path == "/api/auth/login":
        return await call_next(request)

    user_id, tenant_id = _extract_user_info(request)
    start = time()
    response = await call_next(request)
    elapsed = int((time() - start) * 1000)
    response.headers["X-Response-Time-Ms"] = str(elapsed)
    try:
        await track_api_call(user_id, tenant_id, path)
    except Exception as e:
        logger.warning("Stats tracking failed: %s", e)
    return response
