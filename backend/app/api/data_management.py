"""Local-only, explicitly confirmed data lifecycle endpoints."""

from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.api.imports import owner_context
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, engine
from app.schemas.data_management import (
    BackupListResponse,
    BackupResponse,
    ConfirmedDataActionRequest,
    DataConfirmationRequest,
    DataConfirmationResponse,
    DeleteAllResponse,
    LocalDataStatusResponse,
    RestoreResponse,
)
from app.services.backup_service import BackupServiceError
from app.services.data_management_service import DataManagementError, DataManagementService

router = APIRouter(prefix="/data", tags=["local-data"])


def local_data_guard(settings: Settings = Depends(get_settings)) -> None:
    if settings.app_mode not in {"local", "development", "test"}:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "资源不存在"})


def local_action_header(
    value: str | None = Header(default=None, alias="X-PFA-Local-Action"),
) -> None:
    if value != "confirm":
        raise HTTPException(
            status_code=403,
            detail={"code": "LOCAL_ACTION_HEADER_REQUIRED", "message": "缺少本地操作确认 Header"},
        )


@lru_cache
def get_data_management_service() -> DataManagementService:
    return DataManagementService(SessionLocal, engine, settings=get_settings())


def data_management_service() -> DataManagementService:
    return get_data_management_service()


def _call(action):
    try:
        return action()
    except (DataManagementError, BackupServiceError) as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.get(
    "/status",
    response_model=LocalDataStatusResponse,
    dependencies=[Depends(local_data_guard)],
)
def data_status(
    service: DataManagementService = Depends(data_management_service),
) -> LocalDataStatusResponse:
    return _call(service.status)


@router.post(
    "/confirmations",
    response_model=DataConfirmationResponse,
    dependencies=[Depends(local_data_guard), Depends(local_action_header)],
)
def create_confirmation(
    payload: DataConfirmationRequest,
    owner_id: str = Depends(owner_context),
    service: DataManagementService = Depends(data_management_service),
) -> DataConfirmationResponse:
    return _call(lambda: service.issue_confirmation(owner_id, payload))


@router.post(
    "/exports",
    dependencies=[Depends(local_data_guard), Depends(local_action_header)],
)
def export_data(
    payload: ConfirmedDataActionRequest,
    owner_id: str = Depends(owner_context),
    service: DataManagementService = Depends(data_management_service),
) -> Response:
    archive = _call(lambda: service.export_data(owner_id, payload.confirmation_token))
    return Response(
        content=archive.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{archive.filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/backups",
    response_model=BackupListResponse,
    dependencies=[Depends(local_data_guard)],
)
def backups(
    service: DataManagementService = Depends(data_management_service),
) -> BackupListResponse:
    return _call(service.list_backups)


@router.post(
    "/backups",
    response_model=BackupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(local_data_guard), Depends(local_action_header)],
)
def create_backup(
    payload: ConfirmedDataActionRequest,
    owner_id: str = Depends(owner_context),
    service: DataManagementService = Depends(data_management_service),
) -> BackupResponse:
    return _call(lambda: service.create_backup(owner_id, payload.confirmation_token))


@router.post(
    "/backups/{backup_id}/restore",
    response_model=RestoreResponse,
    dependencies=[Depends(local_data_guard), Depends(local_action_header)],
)
def restore_backup(
    backup_id: str,
    payload: ConfirmedDataActionRequest,
    owner_id: str = Depends(owner_context),
    service: DataManagementService = Depends(data_management_service),
) -> RestoreResponse:
    return _call(
        lambda: service.restore_backup(owner_id, backup_id, payload.confirmation_token)
    )


@router.post(
    "/delete-all",
    response_model=DeleteAllResponse,
    dependencies=[Depends(local_data_guard), Depends(local_action_header)],
)
def delete_all(
    payload: ConfirmedDataActionRequest,
    owner_id: str = Depends(owner_context),
    service: DataManagementService = Depends(data_management_service),
) -> DeleteAllResponse:
    return _call(lambda: service.delete_all(owner_id, payload.confirmation_token))
