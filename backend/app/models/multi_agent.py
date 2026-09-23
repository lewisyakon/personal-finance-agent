"""Minimal per-node traces for the fixed stage 7 Multi-Agent workflow."""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.finance import AwareDateTime, utc_now


class AgentStepTrace(Base):
    __tablename__ = "agent_step_traces"
    __table_args__ = (
        Index("ix_agent_step_run_sequence", "run_id", "sequence"),
        Index("ix_agent_step_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    node: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24))
    input_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    output_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)

    run = relationship("AgentRun", back_populates="agent_steps")
