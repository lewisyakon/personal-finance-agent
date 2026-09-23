"""Local-development-only observability endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.imports import owner_context
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.schemas.developer import (
    DeveloperComparisonListResponse,
    DeveloperEvaluationListResponse,
    DeveloperFailureListResponse,
    DeveloperRunDetail,
    DeveloperRunListResponse,
)
from app.services.developer_service import DeveloperService

router = APIRouter(prefix="/developer", tags=["developer"])


def developer_guard(settings: Settings = Depends(get_settings)) -> None:
    if not settings.developer_enabled or settings.app_mode not in {
        "local",
        "development",
        "test",
    }:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "资源不存在"})


def developer_service() -> DeveloperService:
    return DeveloperService(SessionLocal)


@router.get(
    "/runs",
    response_model=DeveloperRunListResponse,
    dependencies=[Depends(developer_guard)],
)
def runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    owner_id: str = Depends(owner_context),
    service: DeveloperService = Depends(developer_service),
) -> DeveloperRunListResponse:
    return service.list_runs(owner_id, page, page_size)


@router.get(
    "/runs/{run_id}",
    response_model=DeveloperRunDetail,
    dependencies=[Depends(developer_guard)],
)
def run_detail(
    run_id: str,
    owner_id: str = Depends(owner_context),
    service: DeveloperService = Depends(developer_service),
) -> DeveloperRunDetail:
    item = service.run_detail(owner_id, run_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "AGENT_RUN_NOT_FOUND", "message": "Agent 运行不存在"},
        )
    return item


@router.get(
    "/eval-runs",
    response_model=DeveloperEvaluationListResponse,
    dependencies=[Depends(developer_guard)],
)
def evaluations(
    owner_id: str = Depends(owner_context),
    service: DeveloperService = Depends(developer_service),
) -> DeveloperEvaluationListResponse:
    return service.list_evaluations(owner_id)


@router.get(
    "/comparisons",
    response_model=DeveloperComparisonListResponse,
    dependencies=[Depends(developer_guard)],
)
def comparisons(
    owner_id: str = Depends(owner_context),
    service: DeveloperService = Depends(developer_service),
) -> DeveloperComparisonListResponse:
    return service.list_comparisons(owner_id)


@router.get(
    "/failures",
    response_model=DeveloperFailureListResponse,
    dependencies=[Depends(developer_guard)],
)
def failures(
    owner_id: str = Depends(owner_context),
    service: DeveloperService = Depends(developer_service),
) -> DeveloperFailureListResponse:
    return service.list_failures(owner_id)
