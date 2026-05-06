import langchain
from langchain.chat_models import init_chat_model

from app.config.settings import get_settings

assert langchain.__version__ >= "1.0.0", f"需要 LangChain 1.0+，当前版本: {langchain.__version__}"


def create_llm(temperature: float = 0):
    settings = get_settings()
    return init_chat_model(
        settings.llm_model,
        model_provider="openai",
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=temperature,
    )
