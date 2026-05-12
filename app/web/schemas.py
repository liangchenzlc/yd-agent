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


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    role: str = Field(pattern="^(employee|admin|super_admin)$")


class AdminUserUpdateRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(employee|admin|super_admin)$")
    enabled: bool | None = None
