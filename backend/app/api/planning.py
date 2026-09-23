"""Stage 8 budget drafts and explicit Agent confirmations."""

from fastapi import APIRouter, Depends, HTTPException

from app.agent.runtime import get_budget_service
from app.api.imports import owner_context
from app.schemas.planning import (
    BudgetDraftRequest,
    BudgetPlanListResponse,
    BudgetPlanResponse,
    BudgetUpdateRequest,
    ConfirmationListResponse,
    ConfirmationResponse,
    ResolveConfirmationRequest,
)
from app.services.budget_service import BudgetService, BudgetServiceError

budget_router = APIRouter(prefix="/budgets", tags=["budgets"])
confirmation_router = APIRouter(prefix="/agent/confirmations", tags=["agent"])


def budget_service() -> BudgetService:
    return get_budget_service()


def _call(action):
    try:
        return action()
    except BudgetServiceError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@budget_router.get("", response_model=BudgetPlanListResponse)
def budgets(
    owner_id: str = Depends(owner_context),
    service: BudgetService = Depends(budget_service),
) -> BudgetPlanListResponse:
    return service.list(owner_id)


@budget_router.post("/drafts", response_model=BudgetPlanResponse)
def create_budget_draft(
    payload: BudgetDraftRequest,
    owner_id: str = Depends(owner_context),
    service: BudgetService = Depends(budget_service),
) -> BudgetPlanResponse:
    budget, _confirmation = _call(
        lambda: service.propose(
            owner_id,
            payload.date_from,
            payload.date_to,
            round(payload.reduction_percent * 100),
        )
    )
    return budget


@budget_router.get("/{budget_id}", response_model=BudgetPlanResponse)
def budget_detail(
    budget_id: str,
    owner_id: str = Depends(owner_context),
    service: BudgetService = Depends(budget_service),
) -> BudgetPlanResponse:
    item = service.get(owner_id, budget_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BUDGET_NOT_FOUND", "message": "预算不存在"},
        )
    return item


@budget_router.patch("/{budget_id}", response_model=BudgetPlanResponse)
def update_budget(
    budget_id: str,
    payload: BudgetUpdateRequest,
    owner_id: str = Depends(owner_context),
    service: BudgetService = Depends(budget_service),
) -> BudgetPlanResponse:
    return _call(lambda: service.update(owner_id, budget_id, payload.proposed_budget_minor))


@confirmation_router.get("", response_model=ConfirmationListResponse)
def confirmations(
    owner_id: str = Depends(owner_context),
    service: BudgetService = Depends(budget_service),
) -> ConfirmationListResponse:
    return service.list_confirmations(owner_id)


@confirmation_router.post("/{confirmation_id}/resolve", response_model=ConfirmationResponse)
def resolve_confirmation(
    confirmation_id: str,
    payload: ResolveConfirmationRequest,
    owner_id: str = Depends(owner_context),
    service: BudgetService = Depends(budget_service),
) -> ConfirmationResponse:
    return _call(lambda: service.resolve_confirmation(owner_id, confirmation_id, payload.decision))
