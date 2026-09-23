"""Stage 11 local data export, deletion, backup, and restore contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DataAction = Literal["export", "delete_all", "backup", "restore"]


class DataConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: DataAction
    confirmation_text: str = Field(min_length=1, max_length=40)
    target_id: str | None = Field(default=None, min_length=32, max_length=32)

    @model_validator(mode="after")
    def validate_target(self) -> "DataConfirmationRequest":
        if self.action == "restore" and self.target_id is None:
            raise ValueError("恢复操作必须指定备份 ID")
        if self.action != "restore" and self.target_id is not None:
            raise ValueError("当前操作不接受目标 ID")
        return self


class DataConfirmationResponse(BaseModel):
    action: DataAction
    target_id: str | None
    confirmation_token: str
    expires_at: datetime


class ConfirmedDataActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_token: str = Field(min_length=32, max_length=128)


class BackupResponse(BaseModel):
    id: str
    kind: Literal["manual", "pre_restore", "pre_upgrade"]
    created_at: datetime
    size_bytes: int = Field(ge=0)
    sha256: str
    schema_fingerprint: str


class BackupListResponse(BaseModel):
    items: list[BackupResponse]
    total: int = Field(ge=0)


class RestoreResponse(BaseModel):
    restored_backup: BackupResponse
    safety_backup: BackupResponse


class DeleteAllResponse(BaseModel):
    deleted_rows: int = Field(ge=0)
    deleted_raw_files: int = Field(ge=0)
    deleted_backup_files: int = Field(ge=0)
    deleted_log_files: int = Field(ge=0)


class LocalDataStatusResponse(BaseModel):
    release_mode: Literal["local_web"] = "local_web"
    data_directory: str
    database_size_bytes: int = Field(ge=0)
    raw_file_count: int = Field(ge=0)
    backup_count: int = Field(ge=0)
    raw_file_ttl_minutes: int = Field(ge=0)
    upgrade_strategy: Literal["backup_before_schema_change"] = "backup_before_schema_change"
