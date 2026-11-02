"""
app/api/v1/endpoints/health.py
---------------------------------
GET /api/v1/health

Simple liveness check. Returns 200 with basic service metadata as long
as the process is running — does not check database connectivity yet
(there's no real database in Phase 2). Useful for uptime checks and as
a smoke test that the frontend can reach the backend at all.
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.common import HealthResponse
from app.utils.time_utils import utc_now

router = APIRouter()


@router.get("", response_model=HealthResponse, summary="Health check")
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        time=utc_now(),
    )
