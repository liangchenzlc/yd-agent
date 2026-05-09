from pydantic import BaseModel, Field


class SupervisorOutput(BaseModel):
    workers: list[str] = Field(default_factory=list, description="选中的 Worker 列表")
    reasoning: str = Field("", description="调度理由")


class RefinerOutput(BaseModel):
    score: int = Field(10, ge=0, le=10)
    faithfulness: bool = True
    relevance: bool = True
    completeness: bool = True
    feedback: str = ""
    retarget_workers: list[str] = []


class MemoryExtractItem(BaseModel):
    type: str = ""  # fact | preference | pattern | template
    content: str = ""
    importance: float = 0.0
    category: str = ""


class MemoryExtractionOutput(BaseModel):
    memories: list[MemoryExtractItem] = []


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


class EntityItem(BaseModel):
    name: str = ""
    type: str = ""
    description: str = ""


class RelationItem(BaseModel):
    source: str = ""
    target: str = ""
    type: str = ""
    description: str = ""


class EntityExtractionOutput(BaseModel):
    entities: list[EntityItem] = []
    relationships: list[RelationItem] = []
