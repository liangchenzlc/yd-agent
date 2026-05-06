from functools import lru_cache
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen3.6-flash"

    # 服务
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # 反思
    max_refinements: int = 2

    # Docker 沙箱
    sandbox_image: str = "python:3.12-slim"
    code_timeout: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
