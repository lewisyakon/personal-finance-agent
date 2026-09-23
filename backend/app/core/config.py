from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration; secrets are read from the environment only."""

    app_mode: str = Field(default="local", validation_alias="APP_MODE")
    developer_enabled: bool = Field(default=True, validation_alias="DEVELOPER_ENABLED")
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
    llm_timeout_seconds: float = Field(
        default=30.0, gt=0, le=600, validation_alias="LLM_TIMEOUT_SECONDS"
    )
    llm_max_retries: int = Field(default=2, ge=0, le=5, validation_alias="LLM_MAX_RETRIES")
    llm_max_output_tokens: int = Field(
        default=1024, ge=64, le=32_768, validation_alias="LLM_MAX_OUTPUT_TOKENS"
    )
    agent_max_context_chars: int = Field(
        default=131_072,
        ge=4096,
        le=2_000_000,
        validation_alias="AGENT_MAX_CONTEXT_CHARS",
    )
    llm_input_cost_per_million_microusd: int = Field(
        default=0,
        ge=0,
        validation_alias="LLM_INPUT_COST_PER_MILLION_MICROUSD",
    )
    llm_output_cost_per_million_microusd: int = Field(
        default=0,
        ge=0,
        validation_alias="LLM_OUTPUT_COST_PER_MILLION_MICROUSD",
    )
    agent_max_steps: int = Field(default=12, ge=2, le=100, validation_alias="AGENT_MAX_STEPS")
    agent_max_tool_calls: int = Field(
        default=8, ge=1, le=50, validation_alias="AGENT_MAX_TOOL_CALLS"
    )
    agent_max_model_calls: int = Field(
        default=8, ge=1, le=50, validation_alias="AGENT_MAX_MODEL_CALLS"
    )
    agent_total_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        le=1800,
        validation_alias="AGENT_TOTAL_TIMEOUT_SECONDS",
    )
    agent_max_total_tokens: int = Field(
        default=32_000, ge=256, le=1_000_000, validation_alias="AGENT_MAX_TOTAL_TOKENS"
    )
    agent_max_replans: int = Field(default=1, ge=0, le=3, validation_alias="AGENT_MAX_REPLANS")
    agent_max_cost_microusd: int = Field(
        default=100_000, ge=0, validation_alias="AGENT_MAX_COST_MICROUSD"
    )
    planner_parallel_workers: int = Field(
        default=4, ge=1, le=8, validation_alias="PLANNER_PARALLEL_WORKERS"
    )
    semantic_auto_apply_threshold: float = Field(
        default=0.85,
        ge=0,
        le=1,
        validation_alias="SEMANTIC_AUTO_APPLY_THRESHOLD",
    )
    semantic_max_categories: int = Field(
        default=100,
        ge=1,
        le=500,
        validation_alias="SEMANTIC_MAX_CATEGORIES",
    )
    tool_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=60,
        validation_alias="TOOL_TIMEOUT_SECONDS",
    )
    tool_max_result_bytes: int = Field(
        default=512 * 1024,
        ge=1024,
        le=10 * 1024 * 1024,
        validation_alias="TOOL_MAX_RESULT_BYTES",
    )
    raw_file_ttl_minutes: int = Field(default=60, validation_alias="RAW_FILE_TTL_MINUTES")
    # Used only for deterministic, owner-scoped fingerprints.  In a hosted
    # deployment this must be supplied through the environment or a secret
    # manager; it is never written to logs or persisted in the database.
    fingerprint_secret: str = Field(
        default="local-development-fingerprint-secret",
        validation_alias="FINGERPRINT_SECRET",
    )
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, validation_alias="MAX_UPLOAD_BYTES")
    archive_max_entries: int = Field(
        default=2000, ge=10, le=20_000, validation_alias="ARCHIVE_MAX_ENTRIES"
    )
    archive_max_uncompressed_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1024,
        le=2 * 1024 * 1024 * 1024,
        validation_alias="ARCHIVE_MAX_UNCOMPRESSED_BYTES",
    )
    archive_max_entry_bytes: int = Field(
        default=25 * 1024 * 1024,
        ge=1024,
        le=512 * 1024 * 1024,
        validation_alias="ARCHIVE_MAX_ENTRY_BYTES",
    )
    archive_max_compression_ratio: int = Field(
        default=200, ge=2, le=10_000, validation_alias="ARCHIVE_MAX_COMPRESSION_RATIO"
    )
    data_export_max_bytes: int = Field(
        default=50 * 1024 * 1024,
        ge=1024,
        le=2 * 1024 * 1024 * 1024,
        validation_alias="DATA_EXPORT_MAX_BYTES",
    )
    backup_max_bytes: int = Field(
        default=2 * 1024 * 1024 * 1024,
        ge=1024,
        le=16 * 1024 * 1024 * 1024,
        validation_alias="BACKUP_MAX_BYTES",
    )
    data_confirmation_ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=1800,
        validation_alias="DATA_CONFIRMATION_TTL_SECONDS",
    )
    local_allowed_hosts: str = Field(
        default="127.0.0.1,localhost,[::1],testserver",
        validation_alias="LOCAL_ALLOWED_HOSTS",
    )
    local_owner_id: str = Field(default="local-owner", validation_alias="LOCAL_OWNER_ID")

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def derive_local_database_url(self) -> "Settings":
        if "database_url" not in self.model_fields_set:
            database_path = (self.data_dir / "personal_finance.db").resolve()
            self.database_url = f"sqlite:///{database_path}"
        return self

    @property
    def allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.local_allowed_hosts.split(",") if item.strip()]

    def ensure_data_dirs(self) -> None:
        (self.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "backups").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_data_dirs()
    return settings
