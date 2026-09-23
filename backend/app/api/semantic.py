"""HTTP API for rule-first semantic transaction classification."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agent.runtime import get_semantic_service
from app.api.imports import owner_context
from app.llm.contracts import ModelProviderError
from app.schemas.semantic import (
    ClassificationSuggestionListResponse,
    ClassificationSuggestionResponse,
    ConfirmClassificationRequest,
    MerchantRuleListResponse,
)
from app.services.semantic_service import SemanticClassificationService, SemanticServiceError

router = APIRouter(prefix="/semantic", tags=["semantic"])


def semantic_service() -> SemanticClassificationService:
    try:
        return get_semantic_service()
    except ModelProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


def _call(action):
    try:
        return action()
    except SemanticServiceError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.post(
    "/transactions/{transaction_id}/classify",
    response_model=ClassificationSuggestionResponse,
)
def classify_transaction(
    transaction_id: int,
    owner_id: str = Depends(owner_context),
    service: SemanticClassificationService = Depends(semantic_service),
) -> ClassificationSuggestionResponse:
    return _call(lambda: service.classify(owner_id, transaction_id))


@router.get("/suggestions", response_model=ClassificationSuggestionListResponse)
def suggestions(
    suggestion_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    owner_id: str = Depends(owner_context),
    service: SemanticClassificationService = Depends(semantic_service),
) -> ClassificationSuggestionListResponse:
    return service.list_suggestions(owner_id, suggestion_status, page, page_size)


@router.post(
    "/suggestions/{suggestion_id}/confirm",
    response_model=ClassificationSuggestionResponse,
)
def confirm_suggestion(
    suggestion_id: str,
    payload: ConfirmClassificationRequest,
    owner_id: str = Depends(owner_context),
    service: SemanticClassificationService = Depends(semantic_service),
) -> ClassificationSuggestionResponse:
    return _call(
        lambda: service.confirm(
            owner_id,
            suggestion_id,
            payload.category,
            save_rule=payload.save_rule,
        )
    )


@router.post(
    "/suggestions/{suggestion_id}/reject",
    response_model=ClassificationSuggestionResponse,
)
def reject_suggestion(
    suggestion_id: str,
    owner_id: str = Depends(owner_context),
    service: SemanticClassificationService = Depends(semantic_service),
) -> ClassificationSuggestionResponse:
    return _call(lambda: service.reject(owner_id, suggestion_id))


@router.get("/rules", response_model=MerchantRuleListResponse)
def rules(
    owner_id: str = Depends(owner_context),
    service: SemanticClassificationService = Depends(semantic_service),
) -> MerchantRuleListResponse:
    return service.list_rules(owner_id)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: str,
    owner_id: str = Depends(owner_context),
    service: SemanticClassificationService = Depends(semantic_service),
) -> None:
    if not service.delete_rule(owner_id, rule_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "MERCHANT_RULE_NOT_FOUND", "message": "商户规则不存在"},
        )
