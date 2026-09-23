"""Strict stage 8 planning, budget, and confirmation contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PlanTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    agent: str = Field(min_length=1, max_length=40)
    objective: str = Field(min_length=1, max_length=300)
    tool_name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any]
    depends_on: list[str] = Field(default_factory=list, max_length=8)


class TaskGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1, le=10)
    allow_replan: bool = False
    tasks: list[PlanTask] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_task_ids(self) -> "TaskGraph":
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("计划任务 ID 重复")
        return self


class PlanValidationIssue(BaseModel):
    code: Literal[
        "UNKNOWN_AGENT",
        "UNKNOWN_TOOL",
        "TOOL_NOT_ALLOWED",
        "INVALID_TOOL_ARGUMENTS",
        "UNKNOWN_DEPENDENCY",
        "SELF_DEPENDENCY",
        "CYCLIC_DEPENDENCY",
    ]
    task_id: str | None = None
    message: str


class PlanValidationResult(BaseModel):
    valid: bool
    issues: list[PlanValidationIssue]
    execution_waves: list[list[str]] = Field(default_factory=list)


class BudgetDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: datetime = Field(alias="from")
    date_to: datetime = Field(alias="to")
    reduction_percent: float = Field(default=10, ge=0, le=50)

    @field_validator("date_from", "date_to")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("预算周期必须包含时区")
        return value

    @model_validator(mode="after")
    def valid_period(self) -> "BudgetDraftRequest":
        if self.date_to <= self.date_from:
            raise ValueError("预算周期结束时间必须晚于开始时间")
        return self


class BudgetUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_budget_minor: int = Field(ge=0, strict=True)


class BudgetPlanResponse(BaseModel):
    id: str
    run_id: str | None
    period_start: datetime
    period_end: datetime
    currency: str
    baseline_expense_minor: int = Field(ge=0)
    proposed_budget_minor: int = Field(ge=0)
    reduction_percent: float = Field(ge=0, le=50)
    status: Literal["draft", "confirmed", "superseded", "rejected"]
    evidence_refs: list[str]
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None


class BudgetPlanListResponse(BaseModel):
    items: list[BudgetPlanResponse]
    total: int = Field(ge=0)


class ConfirmationResponse(BaseModel):
    id: str
    run_id: str | None
    kind: Literal["budget", "disagreement"]
    target_id: str | None
    status: Literal["pending", "confirmed", "rejected"]
    prompt_summary: str
    options: list[str]
    created_at: datetime
    resolved_at: datetime | None = None


class ConfirmationListResponse(BaseModel):
    items: list[ConfirmationResponse]
    total: int = Field(ge=0)


class ResolveConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["confirm", "reject"]
