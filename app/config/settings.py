from functools import lru_cache
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen3.6-flash"

    # 反思
    max_refinements: int = 2

    # Embedding
    embedding_model: str = "text-embedding-v4"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_batch_size: int = 10

    # 存储
    storage_dir: str = "./data/storage"

    # 记忆
    working_memory_ttl_hours: int = 24
    core_memory_limit: int = 500
    memory_extraction_enabled: bool = True
    memory_importance_threshold: float = 0.3

    # Docker 沙箱
    sandbox_image: str = "python:3.12-slim"
    code_timeout: int = 30

    # Eval
    eval_enabled: bool = True
    eval_hard_case_threshold: int = 5
    eval_golden_model: str = ""
    eval_retention_days: int = 30
    eval_maintenance_interval_hours: int = 6

    # Web
    web_secret_key: str = "change-me-in-production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
