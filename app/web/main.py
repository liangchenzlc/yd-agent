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
from app.agent.stats.usage_tracker import track_api_call

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging("data/logs")
    _secret()  # validate WEB_SECRET_KEY on startup
    logger.info("Starting yd-Agent server")
    db.initialize()
    redis_cache.initialize()
    ensure_default_admin()
    logger.info("Server initialization complete")
    yield
    redis_cache.close()
    logger.info("Server shutdown")


app = FastAPI(title="yd-Agent Enterprise Knowledge Desk", version="0.1.0", lifespan=lifespan)

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


def _extract_user_id(request: Request) -> int:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        try:
            return int(decode_token(token).get("sub", 0))
        except Exception:
            logger.warning("Failed to extract user_id from Bearer token", exc_info=True)
            return 0
    cookie = request.cookies.get("access_token")
    if cookie:
        try:
            return int(decode_token(cookie).get("sub", 0))
        except Exception:
            logger.warning("Failed to extract user_id from cookie token", exc_info=True)
            return 0
    return 0


@app.middleware("http")
async def usage_stats_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path == "/api/auth/login":
        return await call_next(request)

    user_id = _extract_user_id(request)
    start = time()
    response = await call_next(request)
    elapsed = int((time() - start) * 1000)
    response.headers["X-Response-Time-Ms"] = str(elapsed)
    await track_api_call(user_id, "default", path)
    return response
