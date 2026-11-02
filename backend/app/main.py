"""
app/main.py
-------------
FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload

Then open:
    http://127.0.0.1:8000/docs      (Swagger UI, auto-generated)
    http://127.0.0.1:8000/redoc     (ReDoc, alternate auto docs)
    http://127.0.0.1:8000/api/v1/health

This module is intentionally small: it creates the app, configures
CORS, mounts the versioned API router, and (optionally) seeds demo
data on startup. All actual logic lives in app/api, app/services, and
app/repositories.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.nlp.qwen_lora_service import get_nlp_service
from app.repositories.factory import chat_repository, location_repository, ride_repository, rider_repository
from app.utils.seed import seed_demo_data

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: seed demo data (mirrors the frontend's mock data) so the
    # API is immediately explorable via Swagger without manual setup.
    if settings.SEED_DEMO_DATA:
        seed_demo_data(
            ride_repo=ride_repository,
            rider_repo=rider_repository,
            location_repo=location_repository,
            chat_repo=chat_repository,
        )
    # Optional NLP model (Phase 3.8): loads in a BACKGROUND thread and only when
    # NLP_ENABLED=true. A no-op by default, so startup is never blocked by the model.
    get_nlp_service().start_background_load()
    yield
    # Shutdown: nothing to clean up yet (no DB connections/pools in Phase 2).


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Backend for ConvoyConnect — NLP-Based Intelligent Group Ride Assistant.\n\n"
        "**Phase 2 status:** foundational REST API only. Data is stored in-memory "
        "(resets on restart). GPS location updates are client-submitted, not live-"
        "streamed. Chat, rides, riders and locations use no NLP/AI. An optional, "
        "**disabled-by-default** intent-prediction endpoint (`POST /api/v1/nlp/predict`, "
        "enabled with `NLP_ENABLED=true`) exposes the Phase 3.7 Qwen2.5 + LoRA classifier; "
        "its output is advisory only and never triggers alerts or actions — see "
        "`app/nlp/README.md`. `app/geospatial` and `app/group_ai` remain planned."
    ),
    lifespan=lifespan,
)

# --- CORS --------------------------------------------------------------
# Allows the React dev server (Vite, default port 5173) to call this API
# from the browser. Adjust settings.CORS_ORIGINS for production domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes --------------------------------------------------------------
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["Root"], summary="API root")
def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
    }
