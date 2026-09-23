"""Developer-only trace and evaluation response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.agent import AgentRunResponse


class DeveloperRunSummary(BaseModel):
    id: str
    status: str
    workflow: str
    provider: str
    model: str
    step_count: int
    tool_call_count: int
    model_call_count: int
    total_tokens: int
    estimated_cost_microusd: int
    duration_ms: int
    error_code: str | None
    started_at: datetime


class DeveloperRunListResponse(BaseModel):
    items: list[DeveloperRunSummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class DeveloperToolTrace(BaseModel):
    evidence_id: str
    tool_name: str
    status: str
    duration_ms: int
    error_code: str | None
    started_at: datetime


class DeveloperPlanTask(BaseModel):
    task_id: str
    agent: str
    tool_name: str
    depends_on: list[str]


class DeveloperPlanTrace(BaseModel):
    version: int
    status: str
    tasks: list[DeveloperPlanTask]
    validation_error_codes: list[str]
    replan_reason: str | None
    created_at: datetime


class DeveloperMemoryAccess(BaseModel):
    status: str
    matched_memory_ids: list[str]
    reason: str
    created_at: datetime


class DeveloperRunDetail(BaseModel):
    run: AgentRunResponse
    tool_traces: list[DeveloperToolTrace]
    plans: list[DeveloperPlanTrace]
    memory_accesses: list[DeveloperMemoryAccess]


class DeveloperEvaluationSummary(BaseModel):
    id: str
    comparison_group_id: str | None
    dataset_version: str
    workflow: str
    provider: str
    model: str
    status: str
    case_count: int
    passed_count: int
    tool_selection_accuracy: float
    numeric_accuracy: float
    task_completion_rate: float
    evidence_coverage: float
    hallucination_rate: float
    routing_accuracy: float
    average_handoff_count: float
    average_latency_ms: int
    p50_latency_ms: int
    p95_latency_ms: int
    total_tokens: int
    estimated_cost_microusd: int
    started_at: datetime


class DeveloperEvaluationListResponse(BaseModel):
    items: list[DeveloperEvaluationSummary]
    total: int = Field(ge=0)


class DeveloperComparison(BaseModel):
    comparison_group_id: str
    dataset_version: str
    items: list[DeveloperEvaluationSummary]


class DeveloperComparisonListResponse(BaseModel):
    items: list[DeveloperComparison]
    total: int = Field(ge=0)


class DeveloperFailureSample(BaseModel):
    id: str
    evaluation_run_id: str
    dataset_version: str
    case_id: str
    workflow: str
    error_stage: str
    error_code: str | None
    summary: dict
    created_at: datetime


class DeveloperFailureListResponse(BaseModel):
    items: list[DeveloperFailureSample]
    total: int = Field(ge=0)
