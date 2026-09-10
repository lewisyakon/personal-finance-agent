from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.imports import BillImportResponse, ImportListResponse
from app.services.import_service import (
    InProcessImportExecutor,
    create_import,
    delete_import,
    ensure_owner,
    get_import,
    import_response,
    list_imports,
)

router = APIRouter(prefix="/imports", tags=["imports"])


def owner_context() -> str:
    # Authentication is intentionally absent in the local MVP.  Keeping this
    # dependency separate makes owner injection explicit and replaceable.
    return get_settings().local_owner_id


def _error(code: str, message: str, http_status: int = 400) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


@router.post("", response_model=BillImportResponse, status_code=status.HTTP_201_CREATED)
async def upload_import(
    file: UploadFile = File(...),
    source: str = Query(default="wechat"),
    format: str | None = Query(default=None),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> BillImportResponse:
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    try:
        item, reused = create_import(
            db,
            owner_id,
            file.filename or "账单.csv",
            content,
            source=source,
            format=format,
        )
    except ValueError as exc:
        raise _error("IMPORT_VALIDATION_ERROR", str(exc)) from exc
    ensure_owner(db, owner_id)
    if not reused:
        item = InProcessImportExecutor(db).execute(item.id, owner_id)
    return import_response(item, idempotent_reuse=reused)


@router.get("", response_model=ImportListResponse)
def imports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> ImportListResponse:
    ensure_owner(db, owner_id)
    return list_imports(db, owner_id, page, page_size)


@router.get("/{import_id}", response_model=BillImportResponse)
def import_detail(
    import_id: str,
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> BillImportResponse:
    item = get_import(db, owner_id, import_id)
    if item is None:
        raise _error("IMPORT_NOT_FOUND", "导入任务不存在", 404)
    return import_response(item)


@router.post("/{import_id}/retry", response_model=BillImportResponse)
def retry_import(
    import_id: str,
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> BillImportResponse:
    item = get_import(db, owner_id, import_id)
    if item is None:
        raise _error("IMPORT_NOT_FOUND", "导入任务不存在", 404)
    # A process can terminate after the task row is marked pending/processing
    # but before its final commit. Re-running is safe because transaction
    # insertion is protected by the owner+fingerprint unique constraint.
    if item.status not in {"pending", "processing", "failed", "partial"}:
        raise _error("IMPORT_NOT_RETRYABLE", "当前状态不允许重试")
    item.status = "pending"
    item.error_summary = None
    db.commit()
    item = InProcessImportExecutor(db).execute(item.id, owner_id)
    return import_response(item)


@router.delete("/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_import(
    import_id: str,
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> None:
    if not delete_import(db, owner_id, import_id):
        raise _error("IMPORT_NOT_FOUND", "导入任务不存在", 404)
