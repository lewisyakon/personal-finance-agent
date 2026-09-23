"""Single-Agent runtime contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentExecutionResult(BaseModel):
    run_id: str
    status: Literal["succeeded", "failed", "cancelled", "needs_confirmation"]
    answer: str
    error_code: str | None = None
    error_message: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    step_count: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    model_call_count: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_microusd: int = Field(default=0, ge=0)
    duration_ms: int = Field(ge=0)


class GroundingResult(BaseModel):
    valid: bool
    unsupported_claims: list[str] = Field(default_factory=list)
