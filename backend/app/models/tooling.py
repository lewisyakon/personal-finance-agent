"""Persistence models for controlled Tool traces and replayable evidence."""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.finance import AwareDateTime, utc_now


class ToolTrace(Base):
    """An owner-scoped, immutable snapshot of one Tool invocation.

    The request never contains ``owner_id``. Ownership comes from the trusted
    runtime context and is stored separately so evidence cannot be replayed
    across workspaces.
    """

    __tablename__ = "tool_traces"
    __table_args__ = (
        Index("ix_tool_trace_owner_started", "owner_id", "started_at"),
        Index("ix_tool_trace_owner_tool", "owner_id", "tool_name"),
    )

    evidence_id: Mapped[str] = mapped_column(String(35), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(64), index=True)
    contract_version: Mapped[str] = mapped_column(String(16), default="1.0")
    status: Mapped[str] = mapped_column(String(16), index=True)
    arguments_json: Mapped[str] = mapped_column(Text, default="{}")
    arguments_sha256: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[str] = mapped_column(Text)
    result_sha256: Mapped[str] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    completed_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
