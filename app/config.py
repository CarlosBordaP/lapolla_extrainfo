"""Application configuration, loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database (local MySQL for dev; swap host/credentials at deploy time) ---
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "polla"
    db_password: str = "polla"
    db_name: str = "polla"
    # Full SQLAlchemy URL override (e.g. sqlite for tests). Empty = assemble MySQL URL.
    db_url: str = ""

    # --- OCR ingestion ---
    ocr_provider: str = "gemini"  # "gemini" | "claude"
    uploads_dir: str = "uploads"  # where OCR screenshots are stored
    # Google Gemini (free tier) — default OCR engine
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    # Anthropic Claude vision (alternative OCR engine)
    anthropic_api_key: str = ""
    ocr_model: str = "claude-opus-4-8"

    # --- Access control ---
    # Comma-separated Golpredictor usernames that may see admin views (stats).
    admin_users: str = ""
    # Set to false to disable manual score entry (once the live API is reliable).
    manual_score_enabled: bool = True

    @property
    def admin_user_set(self) -> set[str]:
        return {u.strip() for u in self.admin_users.split(",") if u.strip()}

    # --- Live score provider (Phase 2) ---
    score_provider: str = "scores365"  # key into scores/ registry
    score_poll_seconds: int = 30
    # Only used by the "worldcup_free" provider (kept as a fallback option).
    score_api_base_url: str = "https://worldcup26.ir"
    score_api_token: str = ""  # free JWT from worldcup_free; unused by scores365

    @property
    def database_url(self) -> str:
        if self.db_url:
            return self.db_url
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
