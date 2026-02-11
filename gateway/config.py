"""
Gateway Configuration
=====================

Pydantic Settings for the Gateway service.
All values can be overridden via environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Gateway configuration (populated from env vars / .env)."""

    # --- Aegra (internal) ---
    aegra_url: str = "http://aegra:8000"

    # --- Database ---
    database_url: str = "postgresql://aicrew:password@postgres:5432/aicrew"

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
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
