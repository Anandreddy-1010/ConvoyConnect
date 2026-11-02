"""
app/core/config.py
-------------------
Centralized application configuration.

Everything environment-specific (allowed CORS origins, app metadata,
future database URLs) lives here so that no other module hardcodes
these values. When Phase 3 introduces PostgreSQL/Firebase, add the
connection settings (DATABASE_URL, FIREBASE_CREDENTIALS_PATH, etc.)
to this same Settings class and read them from environment variables.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- General app metadata -------------------------------------------------
    APP_NAME: str = "ConvoyConnect API"
    APP_VERSION: str = "0.1.0-phase2"
    API_V1_PREFIX: str = "/api/v1"

    # --- CORS -------------------------------------------------------------
    # Origins allowed to call this API from the browser. The React dev
    # server (Vite) typically runs on 5173; CRA defaults to 3000.
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # --- Data layer ---------------------------------------------------------
    # "memory" today. Swap to "postgres" or "firebase" in a later phase;
    # the repository factory in app/repositories reads this flag to decide
    # which concrete repository implementation to construct.
    DATA_BACKEND: str = "memory"

    # Placeholders for future real databases. Unused while DATA_BACKEND
    # == "memory", but declared now so .env files can already define them.
    DATABASE_URL: str = ""
    FIREBASE_CREDENTIALS_PATH: str = ""

    # --- Seed data ------------------------------------------------------
    # If true, main.py seeds one demo ride on startup so the API is
    # immediately testable and lines up with the frontend's mock data.
    SEED_DEMO_DATA: bool = True

    # --- NLP intent prediction (Phase 3.8) -------------------------------------
    # OPTIONAL and OFF by default. When false, nothing is loaded and
    # POST /api/v1/nlp/predict answers 503. The rest of the API is unaffected.
    # The model loads in a background thread, so startup is never blocked.
    NLP_ENABLED: bool = False
    # Empty -> research/nlp/advanced_llm/models/lora_adapter, resolved from this source
    # file's location (NOT the working directory). A relative value is resolved against
    # the repository root; an absolute value is used as-is.
    NLP_ADAPTER_DIR: str = ""
    NLP_BASE_MODEL: str = "Qwen/Qwen2.5-0.5B-Instruct"
    # true -> never contact the Hugging Face Hub (use only the local cache).
    NLP_LOCAL_FILES_ONLY: bool = False
    # How long a request may wait for the single inference slot before getting 503 "busy".
    NLP_QUEUE_TIMEOUT_SECONDS: float = 10.0
    # true -> POST /nlp/predict also returns the model's raw generated text (debugging only).
    NLP_RETURN_RAW_OUTPUT: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance (avoids re-parsing env on every call)."""
    return Settings()
