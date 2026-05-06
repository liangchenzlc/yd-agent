from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息")
    session_id: str | None = Field(None, description="会话 ID（可选）")
    max_refinements: int = Field(2, ge=0, le=5, description="最大反思次数，默认 2")


class WorkerResultItem(BaseModel):
    worker: str
    content: str
    error: str | None = None
    metadata: dict = {}


class ChatResponse(BaseModel):
    answer: str
    reasoning: str = ""
    workers_used: list[str] = []
    worker_results: list[WorkerResultItem] = []
    refinements: int = 0
    session_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_model: str
