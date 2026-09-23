"""Persistence models for Single-Agent runs and privacy-minimized model traces."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.finance import AwareDateTime, utc_now

if TYPE_CHECKING:
    from app.models.multi_agent import AgentStepTrace


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (Index("ix_agent_session_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="新对话")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now, onupdate=utc_now)

    runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentRun.started_at",
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_run_owner_started", "owner_id", "started_at"),
        Index("ix_agent_run_session_started", "session_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    user_query: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    workflow: Mapped[str] = mapped_column(String(24), default="single", index=True)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    model_call_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    tool_names_json: Mapped[str] = mapped_column(Text, default="[]")
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now, onupdate=utc_now)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    session: Mapped[AgentSession] = relationship(back_populates="runs")
    model_calls: Mapped[list["ModelCallTrace"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ModelCallTrace.sequence",
    )
    agent_steps: Mapped[list["AgentStepTrace"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentStepTrace.sequence",
    )


class ModelCallTrace(Base):
    __tablename__ = "model_call_traces"
    __table_args__ = (Index("ix_model_call_run_sequence", "run_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    selected_tools_json: Mapped[str] = mapped_column(Text, default="[]")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)

    run: Mapped[AgentRun] = relationship(back_populates="model_calls")


class AgentEvaluationRun(Base):
    __tablename__ = "agent_evaluation_runs"
    __table_args__ = (Index("ix_agent_eval_owner_started", "owner_id", "started_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    dataset_version: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    workflow: Mapped[str] = mapped_column(String(24), default="single", index=True)
    comparison_group_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_selection_accuracy_bp: Mapped[int] = mapped_column(Integer, default=0)
    numeric_accuracy_bp: Mapped[int] = mapped_column(Integer, default=0)
    average_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    task_completion_bp: Mapped[int] = mapped_column(Integer, default=0)
    evidence_coverage_bp: Mapped[int] = mapped_column(Integer, default=0)
    hallucination_rate_bp: Mapped[int] = mapped_column(Integer, default=0)
    routing_accuracy_bp: Mapped[int] = mapped_column(Integer, default=0)
    average_handoff_count_bp: Mapped[int] = mapped_column(Integer, default=0)
    p50_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    p95_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)


class EvaluationFailureSample(Base):
    __tablename__ = "evaluation_failure_samples"
    __table_args__ = (
        Index("ix_eval_failure_owner_created", "owner_id", "created_at"),
        Index("ix_eval_failure_run_case", "evaluation_run_id", "case_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    dataset_version: Mapped[str] = mapped_column(String(40))
    case_id: Mapped[str] = mapped_column(String(80))
    workflow: Mapped[str] = mapped_column(String(24))
    error_stage: Mapped[str] = mapped_column(String(40))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
