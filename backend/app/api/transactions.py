from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.imports import owner_context
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.imports import (
    CategoryChangeResponse,
    CategoryUpdateRequest,
    TransactionListResponse,
    TransactionResponse,
)
from app.services.import_service import (
    ensure_owner,
    get_transaction,
    list_transactions,
    transaction_response,
    update_category,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _parse_boundary(value: str | None, end: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(get_settings().app_timezone))
        if end and len(value) <= 10:
            # ``to=YYYY-MM-DD`` is inclusive for users, while the service
            # query uses an exclusive upper bound.
            parsed = datetime.combine(
                parsed.date() + timedelta(days=1), datetime.min.time(), tzinfo=parsed.tzinfo
            )
        return parsed.astimezone(UTC).replace(tzinfo=None)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_DATE", "message": "日期格式无效，请使用 ISO-8601"},
        ) from exc


@router.get("", response_model=TransactionListResponse)
def transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    direction: str | None = Query(default=None),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    merchant: str | None = Query(default=None, max_length=120),
    search: str | None = Query(default=None, max_length=120),
    min_amount: int | None = Query(default=None, ge=0),
    max_amount: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> TransactionListResponse:
    ensure_owner(db, owner_id)
    return list_transactions(
        db,
        owner_id,
        page,
        page_size,
        date_from=_parse_boundary(date_from),
        date_to=_parse_boundary(date_to, end=True),
        direction=direction,
        status=status,
        category=category,
        merchant=merchant,
        search=search,
        min_amount=min_amount,
        max_amount=max_amount,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
def transaction_detail(
    transaction_id: int,
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> TransactionResponse:
    item = get_transaction(db, owner_id, transaction_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "TRANSACTION_NOT_FOUND", "message": "交易不存在"},
        )
    return transaction_response(item)


@router.patch("/{transaction_id}/category", response_model=CategoryChangeResponse)
@router.patch("/{transaction_id}", response_model=CategoryChangeResponse)
def category(
    transaction_id: int,
    payload: CategoryUpdateRequest,
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> CategoryChangeResponse:
    change = update_category(
        db, owner_id, transaction_id, payload.category or payload.category_name
    )
    if change is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "TRANSACTION_NOT_FOUND", "message": "交易不存在"},
        )
    return change
