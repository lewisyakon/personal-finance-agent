"""Versioned user-confirmed memories and privacy-minimized retrieval traces."""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.finance import AwareDateTime, utc_now


class MemoryRecord(Base):
    __tablename__ = "memory_records"
    __table_args__ = (
        Index("ix_memory_owner_scope_status", "owner_id", "scope", "status"),
        Index("ix_memory_owner_kind_key", "owner_id", "kind", "memory_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    scope: Mapped[str] = mapped_column(String(24), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    memory_key: Mapped[str] = mapped_column(String(200))
    value_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), default="user_confirmed")
    source_ref_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_records.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now, onupdate=utc_now)


class MemoryAccessTrace(Base):
    __tablename__ = "memory_access_traces"
    __table_args__ = (
        Index("ix_memory_access_owner_created", "owner_id", "created_at"),
        Index("ix_memory_access_run_created", "run_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    query_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), index=True)
    matched_memory_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
