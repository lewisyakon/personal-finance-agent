"""Deterministic Verifier for stage 7 Multi-Agent results."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agent.grounding import validate_numeric_grounding
from app.agent.handoffs import (
    AnalysisHandoff,
    SupervisorHandoff,
    VerificationIssue,
    VerificationResult,
)


def _periods(value: Any) -> list[tuple[datetime, datetime]]:
    found: list[tuple[datetime, datetime]] = []
    if isinstance(value, dict):
        if "start" in value and "end" in value:
            try:
                start = datetime.fromisoformat(str(value["start"]))
                end = datetime.fromisoformat(str(value["end"]))
            except ValueError:
                pass
            else:
                if start.tzinfo is not None and end.tzinfo is not None:
                    found.append((start.astimezone(UTC), end.astimezone(UTC)))
        for item in value.values():
            found.extend(_periods(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_periods(item))
    return found


def _directions(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        direction = value.get("direction")
        if direction in {"expense", "income"}:
            found.add(direction)
        for item in value.values():
            found.update(_directions(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_directions(item))
    return found


def verify_analysis(
    supervisor: SupervisorHandoff,
    analysis: AnalysisHandoff,
) -> VerificationResult:
    issues: list[VerificationIssue] = []
    if analysis.status != "succeeded":
        issues.append(
            VerificationIssue(code="ANALYSIS_FAILED", message="Analysis Agent 未成功完成")
        )
    if not analysis.evidence_refs:
        issues.append(VerificationIssue(code="MISSING_EVIDENCE", message="分析结果缺少 Evidence"))
    grounding = validate_numeric_grounding(analysis.answer, analysis.tool_results)
    if not grounding.valid:
        issues.append(
            VerificationIssue(
                code="UNGROUNDED_AMOUNT",
                message="分析答案包含 Tool 结果无法支持的数字",
            )
        )

    expected_tools = {tool_name for task in supervisor.plan for tool_name in task.required_tools}
    if not expected_tools.issubset(set(analysis.tool_names)):
        issues.append(
            VerificationIssue(
                code="MISSING_PLANNED_TOOL",
                message="Analysis Agent 未执行 Supervisor 要求的 Tool",
            )
        )

    expected_period = (
        supervisor.date_from.astimezone(UTC),
        supervisor.date_to.astimezone(UTC),
    )
    periods = [
        period for result in analysis.tool_results for period in _periods(result.get("data"))
    ]
    if expected_period not in periods:
        issues.append(
            VerificationIssue(
                code="TIME_RANGE_MISMATCH",
                message="Tool Evidence 的时间范围与 Supervisor 约束不一致",
            )
        )

    directions = set()
    for result in analysis.tool_results:
        directions.update(_directions(result.get("data")))
    if (
        supervisor.direction in {"expense", "income"}
        and directions
        and supervisor.direction not in directions
    ):
        issues.append(
            VerificationIssue(
                code="DIRECTION_MISMATCH",
                message="Tool Evidence 的收支方向与问题约束不一致",
            )
        )
    return VerificationResult(
        passed=not issues,
        issues=issues,
        checked_evidence_count=len(analysis.evidence_refs),
    )
