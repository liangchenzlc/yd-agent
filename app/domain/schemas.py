from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息")
    session_id: str | None = Field(None, description="会话 ID（可选）")
    user_id: str = Field("default", description="用户标识")
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
    memories_updated: bool = False


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_model: str


# ----- 文档相关 -----

class DocumentIngestItem(BaseModel):
    id: str = Field("", description="文档 ID，不传则自动生成")
    content: str = Field(..., min_length=1, description="文档内容")
    metadata: dict = Field(default_factory=dict, description="附加元数据")


class DocumentIngestRequest(BaseModel):
    documents: list[DocumentIngestItem] = Field(..., min_length=1, description="待摄入的文档列表")


class DocumentIngestResponse(BaseModel):
    ingested: int = 0
    skipped: int = 0
    total_chunks: int = 0
    total_entities: int = 0
    total_relationships: int = 0


class DocumentStatsResponse(BaseModel):
    total_documents: int = 0
    total_chunks: int = 0
    total_entities: int = 0
    total_relationships: int = 0


class DocumentListItem(BaseModel):
    id: str
    chunks: int = 0
    entities: int = 0


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]


class DocumentDeleteResponse(BaseModel):
    deleted: bool


# ----- 记忆相关 -----

class MemoryItem(BaseModel):
    id: str
    type: str = ""
    content: str = ""
    importance: float = 0.0
    timestamp: str = ""


class MemoryListResponse(BaseModel):
    user_id: str
    core_memories: list[MemoryItem]
    working_memories: list[MemoryItem]


class MemoryDeleteResponse(BaseModel):
    deleted: bool
    user_id: str


class ProfileResponse(BaseModel):
    user_id: str
    topics: dict = {}
    total_interactions: int = 0
    last_active: str = ""


# ----- 评估相关 -----

class EvalDimension(BaseModel):
    name: str = ""
    score: int = 0
    passed: bool = True
    feedback: str = ""


class EvalRunItem(BaseModel):
    run_id: str
    user_id: str
    session_id: str | None = None
    message: str = ""
    answer: str = ""
    worker_results: list[WorkerResultItem] = []
    refinements: int = 0
    overall_score: int = 0
    dimensions: list[EvalDimension] = []
    is_hard_case: bool = False
    timestamp: str = ""


class EvalRunResponse(BaseModel):
    runs: list[EvalRunItem]
    total: int


class HardCaseItem(BaseModel):
    case_id: str
    user_id: str
    message: str
    original_answer: str
    golden_answer: str = ""
    score: int = 0
    timestamp: str = ""
    reviewed: bool = False


class HardCaseListResponse(BaseModel):
    cases: list[HardCaseItem]
    total: int


class EvalSummaryResponse(BaseModel):
    total_eval_runs: int = 0
    total_hard_cases: int = 0
    total_feedback: int = 0
    avg_score: float = 0.0
    pass_rate: float = 0.0
    score_distribution: dict[str, int] = {}
    recent_avg_score: float = 0.0


class FeedbackRequest(BaseModel):
    user_id: str = "default"
    session_id: str | None = None
    thumbs_up: bool
    comment: str = ""
    message: str = ""
    answer: str = ""


class FeedbackItem(BaseModel):
    feedback_id: str
    user_id: str
    session_id: str | None = None
    thumbs_up: bool
    comment: str = ""
    message: str = ""
    answer: str = ""
    timestamp: str = ""


class FeedbackListResponse(BaseModel):
    feedback: list[FeedbackItem]
    total: int
    thumbs_up_count: int
    thumbs_down_count: int
