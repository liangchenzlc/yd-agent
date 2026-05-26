from __future__ import annotations

from pydantic import BaseModel, Field


class AuthRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)


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


class AdminCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=64)


class AdminUpdateRequest(BaseModel):
    enabled: bool | None = None


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserUpdateRequest(BaseModel):
    enabled: bool | None = None


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=128)


class DataSourceRequest(BaseModel):
    db_type: str = Field(default="mysql", pattern="^(mysql|postgresql|sqlite)$")
    db_host: str = Field(default="", max_length=256)
    db_port: int | None = None
    db_user: str = Field(default="", max_length=128)
    db_password: str = Field(default="", max_length=256)
    db_database: str = Field(min_length=1, max_length=1024)


class TenantCreateRequest(BaseModel):
    id: str = Field(min_length=2, max_length=64, pattern="^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    config: dict | None = None


class TenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    config: dict | None = None
