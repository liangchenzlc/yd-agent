from __future__ import annotations

from pydantic import BaseModel, Field


class AuthRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64, description="登录时指定租户，不传则用户名跨租户唯一时可用")


class AuthResponse(BaseModel):
    token: str
    user: dict


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    qa_log_id: int
    workers_used: list[str]
    dispatch_reasoning: str
    worker_results: list[dict]


class FeedbackRequest(BaseModel):
    qa_log_id: int
    rating: int = Field(ge=-1, le=1)
    comment: str = ""


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64, description="不传则默认所属租户")


class AdminUserUpdateRequest(BaseModel):
    enabled: bool | None = None


class TenantCreateRequest(BaseModel):
    id: str = Field(min_length=2, max_length=64, pattern="^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    config: dict | None = None


class TenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    config: dict | None = None
