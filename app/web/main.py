from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.admin import router as admin_router
from app.api.routes.user import router as user_router
from app.web.auth import ensure_default_admin
from app.web.db import db


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    ensure_default_admin()
    yield


app = FastAPI(title="yd-Agent Enterprise Knowledge Desk", version="0.1.0", lifespan=lifespan)
app.include_router(user_router)
app.include_router(admin_router)
