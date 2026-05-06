from fastapi import APIRouter

from app.domain.schemas import HealthResponse
from app.agent._version import __version__
from app.config.settings import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        llm_model=settings.llm_model,
    )
