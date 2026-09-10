from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration; secrets are read from the environment only."""

    app_mode: str = Field(default="local", validation_alias="APP_MODE")
    database_url: str = Field(
        default=f"sqlite:///{PROJECT_ROOT / 'data' / 'personal_finance.db'}",
        validation_alias="DATABASE_URL",
    )
    data_dir: Path = Field(default=PROJECT_ROOT / "data", validation_alias="DATA_DIR")
    app_timezone: str = Field(default="Asia/Shanghai", validation_alias="APP_TIMEZONE")
    llm_provider: str = Field(default="mock", validation_alias="LLM_PROVIDER")
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    llm_model: str = Field(default="mock-model", validation_alias="LLM_MODEL")
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_timeout_seconds: float = Field(default=30.0, validation_alias="LLM_TIMEOUT_SECONDS")
    raw_file_ttl_minutes: int = Field(default=60, validation_alias="RAW_FILE_TTL_MINUTES")
    # Used only for deterministic, owner-scoped fingerprints.  In a hosted
    # deployment this must be supplied through the environment or a secret
    # manager; it is never written to logs or persisted in the database.
    fingerprint_secret: str = Field(
        default="local-development-fingerprint-secret",
        validation_alias="FINGERPRINT_SECRET",
    )
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, validation_alias="MAX_UPLOAD_BYTES")
    local_owner_id: str = Field(default="local-owner", validation_alias="LOCAL_OWNER_ID")

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def ensure_data_dirs(self) -> None:
        (self.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_data_dirs()
    return settings
