from functools import lru_cache
from typing import Literal

from pydantic import ValidationInfo, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal Document Intelligence Agent"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = True

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/personal_doc_agent"

    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: int | None = 1536

    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_top_k: int = 5
    max_report_chunks: int = 12
    retrieval_max_distance: float | None = 0.45
    admin_username: str = "admin"
    admin_password: str = ""
    admin_password_hash: str = ""
    session_secret: str = ""
    session_cookie_name: str = "pda_admin_session"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("DATABASE_URL is missing.")
        return value

    @field_validator("gemini_api_key")
    @classmethod
    def validate_gemini_api_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("admin_username", "admin_password", "admin_password_hash", "session_secret", "session_cookie_name")
    @classmethod
    def validate_auth_strings(cls, value: str) -> str:
        return value.strip()

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, value: int, info: ValidationInfo) -> int:
        chunk_size = info.data.get("chunk_size", 1000)
        if value >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return value

    @computed_field
    @property
    def embedding_dimensions(self) -> int:
        if self.gemini_embedding_dimensions:
            return self.gemini_embedding_dimensions

        defaults = {
            "gemini-embedding-001": 1536,
        }
        return defaults.get(self.gemini_embedding_model, 1536)


@lru_cache
def get_settings() -> Settings:
    return Settings()
