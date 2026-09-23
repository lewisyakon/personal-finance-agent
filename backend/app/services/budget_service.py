"""Deterministic budget drafts with an explicit confirmation gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.planning import AgentConfirmation, BudgetPlan
from app.schemas.planning import (
    BudgetPlanListResponse,
    BudgetPlanResponse,
    ConfirmationListResponse,
    ConfirmationResponse,
)
from app.tools.contracts import OwnerContext, ToolExecutionResult
from app.tools.runtime import ToolExecutor

if TYPE_CHECKING:
    from app.services.memory_service import MemoryService


class BudgetServiceError(ValueError):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def budget_response(item: BudgetPlan) -> BudgetPlanResponse:
    return BudgetPlanResponse(
        id=item.id,
        run_id=item.run_id,
        period_start=_aware(item.period_start),
        period_end=_aware(item.period_end),
        currency=item.currency,
        baseline_expense_minor=item.baseline_expense_minor,
        proposed_budget_minor=item.proposed_budget_minor,
        reduction_percent=item.reduction_bp / 100,
        status=item.status,
        evidence_refs=_json_list(item.evidence_refs_json),
        created_at=_aware(item.created_at),
        updated_at=_aware(item.updated_at),
        confirmed_at=_aware(item.confirmed_at),
    )


def confirmation_response(item: AgentConfirmation) -> ConfirmationResponse:
    return ConfirmationResponse(
        id=item.id,
        run_id=item.run_id,
        kind=item.kind,
        target_id=item.target_id,
        status=item.status,
        prompt_summary=item.prompt_summary,
        options=_json_list(item.options_json),
        created_at=_aware(item.created_at),
        resolved_at=_aware(item.resolved_at),
    )


class BudgetService:
    def __init__(
        self,
        session_factory,
        tool_executor: ToolExecutor,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.tool_executor = tool_executor
        self.memory_service = memory_service

    def propose(
        self,
        owner_id: str,
        date_from: datetime,
        date_to: datetime,
        reduction_bp: int,
        *,
        run_id: str | None = None,
    ) -> tuple[BudgetPlanResponse, ConfirmationResponse]:
        result = self.tool_executor.execute(
            "get_spending_summary",
            {"from": date_from.isoformat(), "to": date_to.isoformat()},
            OwnerContext(owner_id=owner_id),
            run_id=run_id,
        )
        if result.status != "success" or result.data is None:
            raise BudgetServiceError("BUDGET_EVIDENCE_UNAVAILABLE", "预算统计证据不可用")
        return self.propose_from_evidence(owner_id, result, reduction_bp, run_id=run_id)

    def propose_from_evidence(
        self,
        owner_id: str,
        evidence: ToolExecutionResult | dict,
        reduction_bp: int,
        *,
        run_id: str | None = None,
    ) -> tuple[BudgetPlanResponse, ConfirmationResponse]:
        if not 0 <= reduction_bp <= 5000:
            raise BudgetServiceError("INVALID_BUDGET_REDUCTION", "预算压缩比例必须在 0% 到 50%")
        payload = (
            evidence.model_dump(mode="json")
            if isinstance(evidence, ToolExecutionResult)
            else evidence
        )
        if payload.get("status") != "success" or not isinstance(payload.get("data"), dict):
            raise BudgetServiceError("BUDGET_EVIDENCE_UNAVAILABLE", "预算统计证据不可用")
        data = payload["data"]
        period = data.get("period") or {}
        try:
            date_from = datetime.fromisoformat(str(period["start"]))
            date_to = datetime.fromisoformat(str(period["end"]))
            baseline = int(data["expense_minor"])
            currency = str(data["currency"])
            evidence_id = str(payload["evidence_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BudgetServiceError("BUDGET_EVIDENCE_INVALID", "预算统计证据结构无效") from exc
        proposed = baseline * (10_000 - reduction_bp) // 10_000
        now = datetime.now(UTC)
        with self.session_factory() as db:
            item = BudgetPlan(
                id=str(uuid4()),
                owner_id=owner_id,
                run_id=run_id,
                period_start=date_from,
                period_end=date_to,
                currency=currency,
                baseline_expense_minor=baseline,
                proposed_budget_minor=proposed,
                reduction_bp=reduction_bp,
                status="draft",
                evidence_refs_json=json.dumps([evidence_id], separators=(",", ":")),
                created_at=now,
                updated_at=now,
            )
            confirmation = AgentConfirmation(
                id=str(uuid4()),
                owner_id=owner_id,
                run_id=run_id,
                kind="budget",
                target_id=item.id,
                status="pending",
                prompt_summary="确认后此预算草案才会成为长期预算偏好",
                options_json='["confirm","reject"]',
                created_at=now,
            )
            db.add_all((item, confirmation))
            db.commit()
            db.refresh(item)
            db.refresh(confirmation)
            return budget_response(item), confirmation_response(confirmation)

    def list(self, owner_id: str) -> BudgetPlanListResponse:
        with self.session_factory() as db:
            items = list(
                db.scalars(
                    select(BudgetPlan)
                    .where(BudgetPlan.owner_id == owner_id)
                    .order_by(BudgetPlan.created_at.desc())
                )
            )
        return BudgetPlanListResponse(
            items=[budget_response(item) for item in items], total=len(items)
        )

    def get(self, owner_id: str, budget_id: str) -> BudgetPlanResponse | None:
        with self.session_factory() as db:
            item = self._budget(db, owner_id, budget_id, required=False)
            return budget_response(item) if item is not None else None

    def update(self, owner_id: str, budget_id: str, amount_minor: int) -> BudgetPlanResponse:
        with self.session_factory() as db:
            item = self._budget(db, owner_id, budget_id)
            if item.status not in {"draft", "confirmed"}:
                raise BudgetServiceError("BUDGET_NOT_EDITABLE", "当前预算不可修改")
            item.proposed_budget_minor = amount_minor
            item.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(item)
            response = budget_response(item)
        if response.status == "confirmed" and self.memory_service is not None:
            self._remember_budget(owner_id, response)
        return response

    def list_confirmations(self, owner_id: str) -> ConfirmationListResponse:
        with self.session_factory() as db:
            items = list(
                db.scalars(
                    select(AgentConfirmation)
                    .where(AgentConfirmation.owner_id == owner_id)
                    .order_by(AgentConfirmation.created_at.desc())
                )
            )
        return ConfirmationListResponse(
            items=[confirmation_response(item) for item in items], total=len(items)
        )

    def create_disagreement_confirmation(
        self, owner_id: str, run_id: str, summary: str
    ) -> ConfirmationResponse:
        with self.session_factory() as db:
            item = AgentConfirmation(
                id=str(uuid4()),
                owner_id=owner_id,
                run_id=run_id,
                kind="disagreement",
                status="pending",
                prompt_summary=summary[:500],
                options_json='["confirm","reject"]',
                created_at=datetime.now(UTC),
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            return confirmation_response(item)

    def resolve_confirmation(
        self, owner_id: str, confirmation_id: str, decision: str
    ) -> ConfirmationResponse:
        remembered_budget: BudgetPlanResponse | None = None
        with self.session_factory() as db:
            confirmation = db.scalar(
                select(AgentConfirmation).where(
                    AgentConfirmation.id == confirmation_id,
                    AgentConfirmation.owner_id == owner_id,
                )
            )
            if confirmation is None:
                raise BudgetServiceError(
                    "CONFIRMATION_NOT_FOUND", "确认请求不存在", http_status=404
                )
            if confirmation.status != "pending":
                return confirmation_response(confirmation)
            now = datetime.now(UTC)
            confirmation.status = "confirmed" if decision == "confirm" else "rejected"
            confirmation.resolved_at = now
            if confirmation.kind == "budget" and confirmation.target_id:
                budget = self._budget(db, owner_id, confirmation.target_id)
                if decision == "confirm":
                    previous = list(
                        db.scalars(
                            select(BudgetPlan).where(
                                BudgetPlan.owner_id == owner_id,
                                BudgetPlan.status == "confirmed",
                                BudgetPlan.period_start == budget.period_start,
                                BudgetPlan.period_end == budget.period_end,
                                BudgetPlan.id != budget.id,
                            )
                        )
                    )
                    for item in previous:
                        item.status = "superseded"
                        item.updated_at = now
                    budget.status = "confirmed"
                    budget.confirmed_at = now
                    remembered_budget = budget_response(budget)
                else:
                    budget.status = "rejected"
                budget.updated_at = now
            db.commit()
            db.refresh(confirmation)
            response = confirmation_response(confirmation)
        if remembered_budget is not None and self.memory_service is not None:
            self._remember_budget(owner_id, remembered_budget)
        return response

    def _remember_budget(self, owner_id: str, budget: BudgetPlanResponse) -> None:
        if self.memory_service is None:
            return
        self.memory_service.remember(
            owner_id,
            "long_term",
            "budget_preference",
            f"{budget.period_start.isoformat()}_{budget.period_end.isoformat()}",
            {
                "period_start": budget.period_start.isoformat(),
                "period_end": budget.period_end.isoformat(),
                "budget_minor": budget.proposed_budget_minor,
                "currency": budget.currency,
                "reduction_bp": round(budget.reduction_percent * 100),
            },
            source_ref_type="budget_plan",
            source_ref_id=budget.id,
        )

    @staticmethod
    def _budget(
        db: Session, owner_id: str, budget_id: str, *, required: bool = True
    ) -> BudgetPlan | None:
        item = db.scalar(
            select(BudgetPlan).where(
                BudgetPlan.id == budget_id,
                BudgetPlan.owner_id == owner_id,
            )
        )
        if item is None and required:
            raise BudgetServiceError("BUDGET_NOT_FOUND", "预算不存在", http_status=404)
        return item
