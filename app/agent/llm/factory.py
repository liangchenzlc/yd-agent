import langchain
from langchain.chat_models import init_chat_model

from app.config.settings import get_settings

assert langchain.__version__ >= "1.0.0", f"需要 LangChain 1.0+，当前版本: {langchain.__version__}"


def create_llm(temperature: float = 0, model: str | None = None):
    settings = get_settings()
    return init_chat_model(
        model or settings.llm_model,
        model_provider="openai",
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=temperature,
    )


def create_embeddings():
    from langchain_openai import OpenAIEmbeddings

    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.embedding_base_url or settings.llm_base_url,
        api_key=settings.embedding_api_key or settings.llm_api_key,
        check_embedding_ctx_length=False,
        tiktoken_enabled=False,
        chunk_size=settings.embedding_batch_size,
    )


def embed_documents_batched(embeddings_api, texts: list[str], batch_size: int | None = None) -> list[list[float]]:
    """Embed documents in provider-safe batches."""
    if not texts:
        return []

    settings = get_settings()
    size = batch_size or settings.embedding_batch_size
    if size <= 0:
        raise ValueError("embedding_batch_size must be greater than 0")

    embeddings: list[list[float]] = []
    for start in range(0, len(texts), size):
        batch = texts[start:start + size]
        embeddings.extend(embeddings_api.embed_documents(batch))
    return embeddings
