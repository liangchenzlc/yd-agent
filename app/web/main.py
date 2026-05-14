from __future__ import annotations

from contextlib import asynccontextmanager
from time import time

from fastapi import FastAPI, Request

from app.api.routes.admin import router as admin_router
from app.api.routes.user import router as user_router
from app.web.auth import ensure_default_admin
from app.web.db import db
from app.agent.storage.redis_cache import redis_cache
from app.agent.stats.usage_tracker import track_api_call


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    redis_cache.initialize()
    ensure_default_admin()
    yield
    redis_cache.close()


app = FastAPI(title="yd-Agent Enterprise Knowledge Desk", version="0.1.0", lifespan=lifespan)
app.include_router(user_router)
app.include_router(admin_router)


@app.middleware("http")
async def usage_stats_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path == "/api/auth/login":
        return await call_next(request)

    await track_api_call(0, "default", path)
    start = time()
    response = await call_next(request)
    elapsed = int((time() - start) * 1000)
    response.headers["X-Response-Time-Ms"] = str(elapsed)
    return response
