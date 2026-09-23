"""Stage 10 memory management and retrieval trace schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MemoryScope = Literal["session", "long_term", "knowledge"]


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: MemoryScope
    kind: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    key: str = Field(min_length=1, max_length=200)
    value: dict[str, Any]
    expires_at: datetime | None = None

    @field_validator("key")
    @classmethod
    def strip_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("expires_at")
    @classmethod
    def expiry_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("记忆过期时间必须包含时区")
        return value


class MemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any] | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def at_least_one_update(self) -> "MemoryUpdateRequest":
        if self.value is None and self.expires_at is None:
            raise ValueError("至少提供一个待修改字段")
        return self

    @field_validator("expires_at")
    @classmethod
    def update_expiry_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("记忆过期时间必须包含时区")
        return value


class MemoryResponse(BaseModel):
    id: str
    scope: MemoryScope
    kind: str
    key: str
    value: dict[str, Any]
    source: Literal["user_confirmed"]
    source_ref_type: str | None
    source_ref_id: str | None
    status: Literal["active", "superseded", "deleted", "expired"]
    version: int = Field(ge=1)
    supersedes_id: str | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    items: list[MemoryResponse]
    total: int = Field(ge=0)


class MemoryAccessResponse(BaseModel):
    id: str
    run_id: str | None
    status: Literal["hit", "miss"]
    matched_memory_ids: list[str]
    reason: str
    created_at: datetime


class MemoryAccessListResponse(BaseModel):
    items: list[MemoryAccessResponse]
    total: int = Field(ge=0)


class MemoryContext(BaseModel):
    status: Literal["hit", "miss"]
    items: list[MemoryResponse]
    reason: str
