"""Run and persist the stage 5 tool-selection and numeric-grounding baseline."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.agent.runtime import close_agent_runtime, get_agent_service
from app.agent.service import AgentService
from app.core.config import PROJECT_ROOT
from app.db.init import init_database
from app.models.agent import AgentEvaluationRun, EvaluationFailureSample
from app.services.import_service import InProcessImportExecutor, create_import
from app.tools.contracts import OwnerContext

DEFAULT_DATASET = PROJECT_ROOT / "backend" / "evals" / "stage5_questions.json"


class ExpectedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["minor", "count", "percent"]
    value: int | float


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    expected_tools: list[str] = Field(min_length=1)
    expected_facts: list[ExpectedFact] = Field(min_length=1)


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str
    minimum_pass_rate: float = Field(gt=0, le=1)
    cases: list[EvaluationCase] = Field(min_length=30, max_length=30)


class EvaluationCaseResult(BaseModel):
    id: str
    status: str
    passed: bool
    tool_selection_correct: bool
    numeric_fact_count: int
    numeric_fact_matches: int
    selected_tools: list[str]
    error_code: str | None
    latency_ms: int
    total_tokens: int
    evidence_covered: bool
    handoff_count: int
    estimated_cost_microusd: int


class EvaluationReport(BaseModel):
    id: str
    dataset_version: str
    provider: str
    model: str
    workflow: Literal["single", "multi", "multi_unverified", "planner"]
    status: Literal["passed", "failed"]
    case_count: int
    passed_count: int
    pass_rate: float
    minimum_pass_rate: float
    tool_selection_accuracy: float
    numeric_accuracy: float
    average_latency_ms: int
    total_tokens: int
    task_completion_rate: float
    evidence_coverage: float
    hallucination_rate: float
    routing_accuracy: float
    average_handoff_count: float
    p50_latency_ms: int
    p95_latency_ms: int
    estimated_cost_microusd: int
    results: list[EvaluationCaseResult]


class WorkflowComparisonReport(BaseModel):
    dataset_version: str
    single: EvaluationReport
    multi: EvaluationReport
    pass_rate_delta: float
    tool_selection_accuracy_delta: float
    numeric_accuracy_delta: float
    average_latency_delta_ms: int
    total_tokens_delta: int


class ArchitectureComparisonReport(BaseModel):
    comparison_group_id: str
    dataset_version: str
    single: EvaluationReport
    multi_unverified: EvaluationReport
    multi_verified: EvaluationReport


def load_dataset(path: Path = DEFAULT_DATASET) -> EvaluationDataset:
    return EvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _collect_fact_values(
    value: Any,
    path: tuple[str, ...],
    facts: dict[str, set[int | float]],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _collect_fact_values(item, (*path, str(key)), facts)
        return
    if isinstance(value, list):
        for item in value:
            _collect_fact_values(item, path, facts)
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return
    joined = ".".join(path)
    if "_minor" in joined:
        facts["minor"].add(value)
    if "percent" in joined:
        facts["percent"].add(round(float(value), 2))
    if "count" in joined or path[-1:] == ("total",):
        facts["count"].add(value)


def _fact_matches(expected: ExpectedFact, facts: dict[str, set[int | float]]) -> bool:
    target: int | float = expected.value
    if expected.kind == "percent":
        target = round(float(target), 2)
    return target in facts[expected.kind]


def run_evaluation(
    service: AgentService,
    owner_id: str,
    dataset: EvaluationDataset | None = None,
    *,
    workflow: Literal["single", "multi", "multi_unverified", "planner"] = "single",
    comparison_group_id: str | None = None,
) -> EvaluationReport:
    dataset = dataset or load_dataset()
    evaluation_id = str(uuid4())
    started_at = datetime.now(UTC)
    results: list[EvaluationCaseResult] = []
    total_fact_count = 0
    total_fact_matches = 0

    for case in dataset.cases:
        run = service.chat(owner_id, case.question, workflow=workflow)
        tool_correct = run.tool_names == case.expected_tools
        facts: dict[str, set[int | float]] = {
            "minor": set(),
            "count": set(),
            "percent": set(),
        }
        for evidence_id in run.evidence_refs:
            evidence = service.tool_executor.replay(
                evidence_id,
                OwnerContext(owner_id=owner_id),
            )
            if evidence is not None and evidence.data is not None:
                _collect_fact_values(evidence.data, (), facts)
        fact_matches = sum(_fact_matches(expected, facts) for expected in case.expected_facts)
        total_fact_count += len(case.expected_facts)
        total_fact_matches += fact_matches
        passed = (
            run.status == "succeeded" and tool_correct and fact_matches == len(case.expected_facts)
        )
        results.append(
            EvaluationCaseResult(
                id=case.id,
                status=run.status,
                passed=passed,
                tool_selection_correct=tool_correct,
                numeric_fact_count=len(case.expected_facts),
                numeric_fact_matches=fact_matches,
                selected_tools=run.tool_names,
                error_code=run.error_code,
                latency_ms=run.metrics.duration_ms,
                total_tokens=run.metrics.total_tokens,
                evidence_covered=bool(run.evidence_refs),
                handoff_count=max(0, len(run.agent_steps) - 1),
                estimated_cost_microusd=run.metrics.estimated_cost_microusd,
            )
        )

    case_count = len(results)
    passed_count = sum(item.passed for item in results)
    pass_rate = passed_count / case_count
    tool_accuracy = sum(item.tool_selection_correct for item in results) / case_count
    numeric_accuracy = total_fact_matches / total_fact_count
    average_latency_ms = round(sum(item.latency_ms for item in results) / case_count)
    total_tokens = sum(item.total_tokens for item in results)
    task_completion_rate = sum(item.status == "succeeded" for item in results) / case_count
    evidence_coverage = sum(item.evidence_covered for item in results) / case_count
    hallucination_rate = (
        sum(
            item.status == "succeeded" and item.numeric_fact_matches < item.numeric_fact_count
            for item in results
        )
        / case_count
    )
    average_handoff_count = sum(item.handoff_count for item in results) / case_count
    latencies = sorted(item.latency_ms for item in results)
    p50_latency_ms = latencies[max(0, (case_count + 1) // 2 - 1)]
    p95_latency_ms = latencies[max(0, (case_count * 95 + 99) // 100 - 1)]
    estimated_cost_microusd = sum(item.estimated_cost_microusd for item in results)
    status: Literal["passed", "failed"] = (
        "passed" if pass_rate >= dataset.minimum_pass_rate else "failed"
    )
    report = EvaluationReport(
        id=evaluation_id,
        dataset_version=dataset.dataset_version,
        provider=service.provider.provider,
        model=service.provider.model,
        workflow=workflow,
        status=status,
        case_count=case_count,
        passed_count=passed_count,
        pass_rate=pass_rate,
        minimum_pass_rate=dataset.minimum_pass_rate,
        tool_selection_accuracy=tool_accuracy,
        numeric_accuracy=numeric_accuracy,
        average_latency_ms=average_latency_ms,
        total_tokens=total_tokens,
        task_completion_rate=task_completion_rate,
        evidence_coverage=evidence_coverage,
        hallucination_rate=hallucination_rate,
        routing_accuracy=tool_accuracy,
        average_handoff_count=average_handoff_count,
        p50_latency_ms=p50_latency_ms,
        p95_latency_ms=p95_latency_ms,
        estimated_cost_microusd=estimated_cost_microusd,
        results=results,
    )

    with service.session_factory() as db:
        db.add(
            AgentEvaluationRun(
                id=evaluation_id,
                owner_id=owner_id,
                dataset_version=dataset.dataset_version,
                provider=service.provider.provider,
                model=service.provider.model,
                workflow=workflow,
                comparison_group_id=comparison_group_id,
                status=status,
                case_count=case_count,
                passed_count=passed_count,
                tool_selection_accuracy_bp=round(tool_accuracy * 10_000),
                numeric_accuracy_bp=round(numeric_accuracy * 10_000),
                average_latency_ms=average_latency_ms,
                total_tokens=total_tokens,
                task_completion_bp=round(task_completion_rate * 10_000),
                evidence_coverage_bp=round(evidence_coverage * 10_000),
                hallucination_rate_bp=round(hallucination_rate * 10_000),
                routing_accuracy_bp=round(tool_accuracy * 10_000),
                average_handoff_count_bp=round(average_handoff_count * 100),
                p50_latency_ms=p50_latency_ms,
                p95_latency_ms=p95_latency_ms,
                estimated_cost_microusd=estimated_cost_microusd,
                results_json=json.dumps(
                    [item.model_dump(mode="json") for item in results],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
        )
        for item in results:
            if item.passed:
                continue
            error_stage = "model"
            if item.error_code and "TOOL" in item.error_code:
                error_stage = "tool"
            elif item.error_code and "PLAN" in item.error_code:
                error_stage = "planning"
            elif item.error_code and "VERIFICATION" in item.error_code:
                error_stage = "verification"
            elif not item.tool_selection_correct:
                error_stage = "routing"
            elif item.numeric_fact_matches < item.numeric_fact_count:
                error_stage = "grounding"
            db.add(
                EvaluationFailureSample(
                    id=str(uuid4()),
                    evaluation_run_id=evaluation_id,
                    owner_id=owner_id,
                    dataset_version=dataset.dataset_version,
                    case_id=item.id,
                    workflow=workflow,
                    error_stage=error_stage,
                    error_code=item.error_code,
                    summary_json=json.dumps(
                        {
                            "status": item.status,
                            "selected_tools": item.selected_tools,
                            "numeric_fact_matches": item.numeric_fact_matches,
                            "numeric_fact_count": item.numeric_fact_count,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    created_at=datetime.now(UTC),
                )
            )
        db.commit()
    return report


def run_workflow_comparison(
    service: AgentService,
    owner_id: str,
    dataset: EvaluationDataset | None = None,
) -> WorkflowComparisonReport:
    """Run the same deterministic dataset through both workflows."""

    selected_dataset = dataset or load_dataset()
    single = run_evaluation(
        service,
        owner_id,
        selected_dataset,
        workflow="single",
    )
    multi = run_evaluation(
        service,
        owner_id,
        selected_dataset,
        workflow="multi",
    )
    return WorkflowComparisonReport(
        dataset_version=selected_dataset.dataset_version,
        single=single,
        multi=multi,
        pass_rate_delta=multi.pass_rate - single.pass_rate,
        tool_selection_accuracy_delta=(
            multi.tool_selection_accuracy - single.tool_selection_accuracy
        ),
        numeric_accuracy_delta=multi.numeric_accuracy - single.numeric_accuracy,
        average_latency_delta_ms=(multi.average_latency_ms - single.average_latency_ms),
        total_tokens_delta=multi.total_tokens - single.total_tokens,
    )


def run_architecture_comparison(
    service: AgentService,
    owner_id: str,
    dataset: EvaluationDataset | None = None,
) -> ArchitectureComparisonReport:
    selected_dataset = dataset or load_dataset()
    comparison_group_id = str(uuid4())
    single = run_evaluation(
        service,
        owner_id,
        selected_dataset,
        workflow="single",
        comparison_group_id=comparison_group_id,
    )
    multi_unverified = run_evaluation(
        service,
        owner_id,
        selected_dataset,
        workflow="multi_unverified",
        comparison_group_id=comparison_group_id,
    )
    multi_verified = run_evaluation(
        service,
        owner_id,
        selected_dataset,
        workflow="multi",
        comparison_group_id=comparison_group_id,
    )
    return ArchitectureComparisonReport(
        comparison_group_id=comparison_group_id,
        dataset_version=selected_dataset.dataset_version,
        single=single,
        multi_unverified=multi_unverified,
        multi_verified=multi_verified,
    )


def import_evaluation_fixture(service: AgentService, owner_id: str, path: Path) -> None:
    """Import an explicitly selected synthetic fixture before an isolated eval."""

    with service.session_factory() as db:
        item, reused = create_import(db, owner_id, path.name, path.read_bytes())
        if not reused:
            item = InProcessImportExecutor(db).execute(item.id, owner_id)
        if item.status != "completed":
            raise RuntimeError("评测夹具导入失败")


def main() -> int:
    parser = argparse.ArgumentParser(description="运行阶段 5/7 Agent 评测")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--owner-id", default="stage5-eval-owner")
    parser.add_argument(
        "--fixture",
        type=Path,
        help="可选：先把明确指定的脱敏 CSV/XLSX 夹具导入评测 Owner",
    )
    parser.add_argument(
        "--workflow",
        choices=("single", "multi", "multi_unverified", "planner", "compare", "architecture"),
        default="single",
        help="固定工作流；compare 会在同一数据集上依次运行两种工作流",
    )
    args = parser.parse_args()
    init_database()
    try:
        service = get_agent_service()
        if args.fixture is not None:
            import_evaluation_fixture(service, args.owner_id, args.fixture)
        dataset = load_dataset(args.dataset)
        if args.workflow == "architecture":
            report = run_architecture_comparison(service, args.owner_id, dataset)
            passed = all(
                item.status == "passed"
                for item in (report.single, report.multi_unverified, report.multi_verified)
            )
        elif args.workflow == "compare":
            report = run_workflow_comparison(service, args.owner_id, dataset)
            passed = report.single.status == report.multi.status == "passed"
        else:
            report = run_evaluation(
                service,
                args.owner_id,
                dataset,
                workflow=args.workflow,
            )
            passed = report.status == "passed"
        print(report.model_dump_json(indent=2))
        return 0 if passed else 1
    finally:
        close_agent_runtime()


if __name__ == "__main__":
    raise SystemExit(main())
