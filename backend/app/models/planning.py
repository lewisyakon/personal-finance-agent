"""Stage 8 task plans, budget drafts, and explicit confirmations."""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.finance import AwareDateTime, utc_now


class AgentPlanTrace(Base):
    __tablename__ = "agent_plan_traces"
    __table_args__ = (
        Index("ix_agent_plan_run_version", "run_id", "version"),
        Index("ix_agent_plan_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    plan_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_errors_json: Mapped[str] = mapped_column(Text, default="[]")
    replan_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)


class BudgetPlan(Base):
    __tablename__ = "budget_plans"
    __table_args__ = (
        Index("ix_budget_plan_owner_status", "owner_id", "status"),
        Index("ix_budget_plan_owner_period", "owner_id", "period_start", "period_end"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    period_start: Mapped[datetime] = mapped_column(AwareDateTime())
    period_end: Mapped[datetime] = mapped_column(AwareDateTime())
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    baseline_expense_minor: Mapped[int] = mapped_column(Integer)
    proposed_budget_minor: Mapped[int] = mapped_column(Integer)
    reduction_bp: Mapped[int] = mapped_column(Integer, default=1000)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now, onupdate=utc_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)


class AgentConfirmation(Base):
    __tablename__ = "agent_confirmations"
    __table_args__ = (
        Index("ix_agent_confirmation_owner_status", "owner_id", "status"),
        Index("ix_agent_confirmation_run", "run_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    prompt_summary: Mapped[str] = mapped_column(String(500))
    options_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
