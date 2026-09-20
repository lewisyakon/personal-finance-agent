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
from app.models.agent import AgentEvaluationRun
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


class EvaluationReport(BaseModel):
    id: str
    dataset_version: str
    provider: str
    model: str
    status: Literal["passed", "failed"]
    case_count: int
    passed_count: int
    pass_rate: float
    minimum_pass_rate: float
    tool_selection_accuracy: float
    numeric_accuracy: float
    average_latency_ms: int
    total_tokens: int
    results: list[EvaluationCaseResult]


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
) -> EvaluationReport:
    dataset = dataset or load_dataset()
    evaluation_id = str(uuid4())
    started_at = datetime.now(UTC)
    results: list[EvaluationCaseResult] = []
    total_fact_count = 0
    total_fact_matches = 0

    for case in dataset.cases:
        run = service.chat(owner_id, case.question)
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
            )
        )

    case_count = len(results)
    passed_count = sum(item.passed for item in results)
    pass_rate = passed_count / case_count
    tool_accuracy = sum(item.tool_selection_correct for item in results) / case_count
    numeric_accuracy = total_fact_matches / total_fact_count
    average_latency_ms = round(sum(item.latency_ms for item in results) / case_count)
    total_tokens = sum(item.total_tokens for item in results)
    status: Literal["passed", "failed"] = (
        "passed" if pass_rate >= dataset.minimum_pass_rate else "failed"
    )
    report = EvaluationReport(
        id=evaluation_id,
        dataset_version=dataset.dataset_version,
        provider=service.provider.provider,
        model=service.provider.model,
        status=status,
        case_count=case_count,
        passed_count=passed_count,
        pass_rate=pass_rate,
        minimum_pass_rate=dataset.minimum_pass_rate,
        tool_selection_accuracy=tool_accuracy,
        numeric_accuracy=numeric_accuracy,
        average_latency_ms=average_latency_ms,
        total_tokens=total_tokens,
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
                status=status,
                case_count=case_count,
                passed_count=passed_count,
                tool_selection_accuracy_bp=round(tool_accuracy * 10_000),
                numeric_accuracy_bp=round(numeric_accuracy * 10_000),
                average_latency_ms=average_latency_ms,
                total_tokens=total_tokens,
                results_json=json.dumps(
                    [item.model_dump(mode="json") for item in results],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
        )
        db.commit()
    return report


def import_evaluation_fixture(service: AgentService, owner_id: str, path: Path) -> None:
    """Import an explicitly selected synthetic fixture before an isolated eval."""

    with service.session_factory() as db:
        item, reused = create_import(db, owner_id, path.name, path.read_bytes())
        if not reused:
            item = InProcessImportExecutor(db).execute(item.id, owner_id)
        if item.status != "completed":
            raise RuntimeError("评测夹具导入失败")


def main() -> int:
    parser = argparse.ArgumentParser(description="运行阶段 5 Single-Agent 评测")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--owner-id", default="stage5-eval-owner")
    parser.add_argument(
        "--fixture",
        type=Path,
        help="可选：先把明确指定的脱敏 CSV/XLSX 夹具导入评测 Owner",
    )
    args = parser.parse_args()
    init_database()
    try:
        service = get_agent_service()
        if args.fixture is not None:
            import_evaluation_fixture(service, args.owner_id, args.fixture)
        report = run_evaluation(
            service,
            args.owner_id,
            load_dataset(args.dataset),
        )
        print(report.model_dump_json(indent=2))
        return 0 if report.status == "passed" else 1
    finally:
        close_agent_runtime()


if __name__ == "__main__":
    raise SystemExit(main())
