from pydantic import BaseModel, Field, field_validator, model_validator


class SupervisorOutput(BaseModel):
    workers: list[str] = Field(default_factory=list, description="选中的 Worker 列表")
    reasoning: str = Field("", description="调度理由")

    @field_validator("workers", mode="before")
    @classmethod
    def coerce_workers(cls, v):
        """兼容 LLM 返回 [{'name': 'summary'}, ...] 的情况。"""
        if isinstance(v, list):
            return [w.get("name", "") if isinstance(w, dict) else str(w) for w in v]
        return v


class RefinerOutput(BaseModel):
    score: int = Field(10, ge=0, le=10)
    faithfulness: bool = True
    relevance: bool = True
    completeness: bool = True
    feedback: str = ""
    retarget_workers: list[str] = []

    @field_validator("faithfulness", "relevance", "completeness", mode="before")
    @classmethod
    def coerce_bool(cls, v):
        """兼容 LLM 返回 int 评分的情况。"""
        if isinstance(v, (int, float)):
            return v >= 5
        return bool(v)


class MemoryExtractItem(BaseModel):
    type: str = ""  # fact | preference | pattern | template
    content: str = ""
    importance: float = 0.0
    category: str = ""


class MemoryExtractionOutput(BaseModel):
    memories: list[MemoryExtractItem] = []

    @model_validator(mode="before")
    @classmethod
    def coerce_root_list_to_dict(cls, v):
        """兼容 LLM 返回裸列表的情况（qwen 可能返回 [] 而非 {"memories": []}）。"""
        if isinstance(v, list):
            return {"memories": v}
        return v


class EvalDimension(BaseModel):
    score: int = 0
    passed: bool = False
    feedback: str = ""


class EvaluationOutput(BaseModel):
    faithfulness: EvalDimension = Field(default_factory=EvalDimension)
    relevance: EvalDimension = Field(default_factory=EvalDimension)
    completeness: EvalDimension = Field(default_factory=EvalDimension)
    overall_score: int = 0
    is_hard_case: bool = False
    summary: str = ""


class KeywordOutput(BaseModel):
    ll_keywords: list[str] = []
    hl_keywords: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def coerce_root_list_to_dict(cls, v):
        if isinstance(v, list):
            return {"ll_keywords": [], "hl_keywords": []}
        return v


