"""Owner-scoped, privacy-minimized observability queries for local development."""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.agent.service import run_response
from app.models.agent import AgentEvaluationRun, AgentRun, EvaluationFailureSample
from app.models.memory import MemoryAccessTrace
from app.models.planning import AgentPlanTrace
from app.models.tooling import ToolTrace
from app.schemas.developer import (
    DeveloperComparison,
    DeveloperComparisonListResponse,
    DeveloperEvaluationListResponse,
    DeveloperEvaluationSummary,
    DeveloperFailureListResponse,
    DeveloperFailureSample,
    DeveloperMemoryAccess,
    DeveloperPlanTask,
    DeveloperPlanTrace,
    DeveloperRunDetail,
    DeveloperRunListResponse,
    DeveloperRunSummary,
    DeveloperToolTrace,
)


def _json(value: str, fallback):
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return fallback
    return parsed


def _evaluation(item: AgentEvaluationRun) -> DeveloperEvaluationSummary:
    return DeveloperEvaluationSummary(
        id=item.id,
        comparison_group_id=item.comparison_group_id,
        dataset_version=item.dataset_version,
        workflow=item.workflow,
        provider=item.provider,
        model=item.model,
        status=item.status,
        case_count=item.case_count,
        passed_count=item.passed_count,
        tool_selection_accuracy=item.tool_selection_accuracy_bp / 10_000,
        numeric_accuracy=item.numeric_accuracy_bp / 10_000,
        task_completion_rate=item.task_completion_bp / 10_000,
        evidence_coverage=item.evidence_coverage_bp / 10_000,
        hallucination_rate=item.hallucination_rate_bp / 10_000,
        routing_accuracy=item.routing_accuracy_bp / 10_000,
        average_handoff_count=item.average_handoff_count_bp / 100,
        average_latency_ms=item.average_latency_ms,
        p50_latency_ms=item.p50_latency_ms,
        p95_latency_ms=item.p95_latency_ms,
        total_tokens=item.total_tokens,
        estimated_cost_microusd=item.estimated_cost_microusd,
        started_at=item.started_at,
    )


class DeveloperService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def list_runs(self, owner_id: str, page: int, page_size: int) -> DeveloperRunListResponse:
        query = select(AgentRun).where(AgentRun.owner_id == owner_id)
        with self.session_factory() as db:
            total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
            rows = list(
                db.scalars(
                    query.order_by(AgentRun.started_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
        return DeveloperRunListResponse(
            items=[
                DeveloperRunSummary(
                    id=item.id,
                    status=item.status,
                    workflow=item.workflow,
                    provider=item.provider,
                    model=item.model,
                    step_count=item.step_count,
                    tool_call_count=item.tool_call_count,
                    model_call_count=item.model_call_count,
                    total_tokens=item.total_tokens,
                    estimated_cost_microusd=item.estimated_cost_microusd,
                    duration_ms=item.duration_ms,
                    error_code=item.error_code,
                    started_at=item.started_at,
                )
                for item in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    def run_detail(self, owner_id: str, run_id: str) -> DeveloperRunDetail | None:
        with self.session_factory() as db:
            run = db.scalar(
                select(AgentRun)
                .options(
                    selectinload(AgentRun.model_calls),
                    selectinload(AgentRun.agent_steps),
                )
                .where(AgentRun.id == run_id, AgentRun.owner_id == owner_id)
            )
            if run is None:
                return None
            tools = list(
                db.scalars(
                    select(ToolTrace)
                    .where(ToolTrace.run_id == run_id, ToolTrace.owner_id == owner_id)
                    .order_by(ToolTrace.started_at)
                )
            )
            plans = list(
                db.scalars(
                    select(AgentPlanTrace)
                    .where(AgentPlanTrace.run_id == run_id, AgentPlanTrace.owner_id == owner_id)
                    .order_by(AgentPlanTrace.version)
                )
            )
            memory_accesses = list(
                db.scalars(
                    select(MemoryAccessTrace)
                    .where(
                        MemoryAccessTrace.run_id == run_id,
                        MemoryAccessTrace.owner_id == owner_id,
                    )
                    .order_by(MemoryAccessTrace.created_at)
                )
            )
            return DeveloperRunDetail(
                run=run_response(run),
                tool_traces=[
                    DeveloperToolTrace(
                        evidence_id=item.evidence_id,
                        tool_name=item.tool_name,
                        status=item.status,
                        duration_ms=item.duration_ms,
                        error_code=item.error_code,
                        started_at=item.started_at,
                    )
                    for item in tools
                ],
                plans=[self._plan_response(item) for item in plans],
                memory_accesses=[
                    DeveloperMemoryAccess(
                        status=item.status,
                        matched_memory_ids=[
                            str(value)
                            for value in _json(item.matched_memory_ids_json, [])
                        ],
                        reason=item.reason,
                        created_at=item.created_at,
                    )
                    for item in memory_accesses
                ],
            )

    def list_evaluations(self, owner_id: str) -> DeveloperEvaluationListResponse:
        with self.session_factory() as db:
            rows = list(
                db.scalars(
                    select(AgentEvaluationRun)
                    .where(AgentEvaluationRun.owner_id == owner_id)
                    .order_by(AgentEvaluationRun.started_at.desc())
                    .limit(100)
                )
            )
        return DeveloperEvaluationListResponse(
            items=[_evaluation(item) for item in rows], total=len(rows)
        )

    def list_comparisons(self, owner_id: str) -> DeveloperComparisonListResponse:
        with self.session_factory() as db:
            rows = list(
                db.scalars(
                    select(AgentEvaluationRun)
                    .where(
                        AgentEvaluationRun.owner_id == owner_id,
                        AgentEvaluationRun.comparison_group_id.is_not(None),
                    )
                    .order_by(AgentEvaluationRun.started_at.desc())
                    .limit(300)
                )
            )
        grouped: dict[str, list[AgentEvaluationRun]] = {}
        for item in rows:
            if item.comparison_group_id:
                grouped.setdefault(item.comparison_group_id, []).append(item)
        items = [
            DeveloperComparison(
                comparison_group_id=group_id,
                dataset_version=group[0].dataset_version,
                items=[_evaluation(item) for item in group],
            )
            for group_id, group in grouped.items()
        ]
        return DeveloperComparisonListResponse(items=items, total=len(items))

    def list_failures(self, owner_id: str) -> DeveloperFailureListResponse:
        with self.session_factory() as db:
            rows = list(
                db.scalars(
                    select(EvaluationFailureSample)
                    .where(EvaluationFailureSample.owner_id == owner_id)
                    .order_by(EvaluationFailureSample.created_at.desc())
                    .limit(200)
                )
            )
        return DeveloperFailureListResponse(
            items=[
                DeveloperFailureSample(
                    id=item.id,
                    evaluation_run_id=item.evaluation_run_id,
                    dataset_version=item.dataset_version,
                    case_id=item.case_id,
                    workflow=item.workflow,
                    error_stage=item.error_stage,
                    error_code=item.error_code,
                    summary=_json(item.summary_json, {}),
                    created_at=item.created_at,
                )
                for item in rows
            ],
            total=len(rows),
        )

    @staticmethod
    def _plan_response(item: AgentPlanTrace) -> DeveloperPlanTrace:
        plan = _json(item.plan_json, {})
        issues = _json(item.validation_errors_json, [])
        return DeveloperPlanTrace(
            version=item.version,
            status=item.status,
            tasks=[
                DeveloperPlanTask(
                    task_id=str(task.get("task_id", "")),
                    agent=str(task.get("agent", "")),
                    tool_name=str(task.get("tool_name", "")),
                    depends_on=[str(value) for value in task.get("depends_on", [])],
                )
                for task in plan.get("tasks", [])
                if isinstance(task, dict)
            ],
            validation_error_codes=[
                str(issue.get("code")) for issue in issues if isinstance(issue, dict)
            ],
            replan_reason=item.replan_reason,
            created_at=item.created_at,
        )
