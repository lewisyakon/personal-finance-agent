"""Strict handoff contracts for the fixed stage 7 Agent graph."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AnalysisTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=64)
    agent: Literal["analysis"]
    objective: str = Field(min_length=1, max_length=300)
    required_tools: list[str] = Field(min_length=1, max_length=4)


class SupervisorHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_intent: str = Field(min_length=1, max_length=200)
    date_from: datetime
    date_to: datetime
    direction: Literal["expense", "income", "all"]
    plan: list[AnalysisTask] = Field(min_length=1, max_length=3)

    @field_validator("date_from", "date_to")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Handoff 时间必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_period(self) -> SupervisorHandoff:
        if self.date_to <= self.date_from:
            raise ValueError("Handoff 结束时间必须晚于开始时间")
        return self


class AnalysisHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["succeeded", "failed", "cancelled"]
    answer: str
    evidence_refs: list[str]
    tool_names: list[str]
    tool_results: list[dict[str, Any]] = Field(exclude=True)
    error_code: str | None
    error_message: str | None


class VerificationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "MISSING_EVIDENCE",
        "UNGROUNDED_AMOUNT",
        "TIME_RANGE_MISMATCH",
        "DIRECTION_MISMATCH",
        "MISSING_PLANNED_TOOL",
        "ANALYSIS_FAILED",
    ]
    message: str


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    issues: list[VerificationIssue]
    checked_evidence_count: int = Field(ge=0)


class TokenUsageState(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
