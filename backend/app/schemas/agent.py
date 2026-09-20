"""HTTP schemas for Single-Agent sessions and runs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("消息不能为空")
        return stripped


class AgentMetrics(BaseModel):
    step_count: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    model_call_count: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class ModelCallTraceResponse(BaseModel):
    sequence: int = Field(ge=1)
    status: str
    provider: str
    model: str
    latency_ms: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    selected_tools: list[str]
    error_code: str | None = None
    created_at: datetime


class AgentRunResponse(BaseModel):
    id: str
    session_id: str
    status: Literal["running", "succeeded", "failed", "cancelled"]
    user_query: str
    answer: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    provider: str
    model: str
    evidence_refs: list[str]
    tool_names: list[str]
    metrics: AgentMetrics
    cancellation_requested: bool
    started_at: datetime
    completed_at: datetime | None = None
    model_calls: list[ModelCallTraceResponse] = Field(default_factory=list)


class AgentSessionSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    run_count: int = Field(ge=0)


class AgentSessionListResponse(BaseModel):
    items: list[AgentSessionSummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class AgentSessionResponse(AgentSessionSummary):
    runs: list[AgentRunResponse]
