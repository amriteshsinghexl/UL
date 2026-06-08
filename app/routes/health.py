from fastapi import APIRouter
from app.core.config import settings
from app.schemas.responses import HealthResponse

router = APIRouter(tags=["Health"])

VERSION = "2.0.0"


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=VERSION,
        base_dir=settings.base_dir,
    )
