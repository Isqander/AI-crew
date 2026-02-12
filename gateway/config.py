"""
Gateway Configuration
=====================

Pydantic Settings for the Gateway service.
All values can be overridden via environment variables.

CORS_ORIGINS can be set as a JSON array or comma-separated list:
  CORS_ORIGINS='["http://localhost:5173","https://front.example.com"]'
  CORS_ORIGINS='http://localhost:5173,https://front.example.com'
"""

import json
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Gateway configuration (populated from env vars / .env)."""

    # --- Aegra (internal) ---
    aegra_url: str = "http://aegra:8000"

    # --- Database ---
    database_url: str = "postgresql://aicrew:password@postgres:5433/aicrew"

    # --- JWT ---
    jwt_secret: str = "change-me-in-production"
    jwt_access_ttl: int = 1800        # 30 minutes (seconds)
    jwt_refresh_ttl: int = 604800     # 7 days (seconds)
    jwt_algorithm: str = "HS256"

    # --- LLM (for Switch-Agent router) ---
    llm_api_url: str = ""
    llm_api_key: str = ""

    # --- Logging ---
    log_level: str = "INFO"
    env_mode: str = "LOCAL"

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3001"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Accept JSON array string or comma-separated string."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
