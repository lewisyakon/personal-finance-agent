from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.imports import owner_context
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.stats import (
    BudgetResponse,
    CategoryBreakdown,
    ComparisonResponse,
    FixedVariableBreakdown,
    LargeTransactionResponse,
    MerchantRanking,
    StatsSummary,
    TrendResponse,
)
from app.services.stats_service import (
    Period,
    compare_periods,
    default_period,
    get_budget_status,
    get_category_breakdown,
    get_fixed_variable,
    get_large_transactions,
    get_summary,
    get_top_merchants,
    get_trend,
    make_period,
    period_response,
)

router = APIRouter(prefix="/stats", tags=["stats"])


def _parse_datetime(value: str | None, *, end: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_DATE", "message": "日期格式无效，请使用 ISO-8601"},
        ) from exc
    timezone = ZoneInfo(get_settings().app_timezone)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    if end and len(value) == 10:
        parsed = parsed + timedelta(days=1)
    return parsed.astimezone(UTC)


def _period(
    date_from: str | None,
    date_to: str | None,
) -> Period:
    if not date_from and not date_to:
        return default_period()
    start = _parse_datetime(date_from)
    end = _parse_datetime(date_to, end=True)
    if start is None and end is not None:
        start = end - timedelta(days=30)
    if start is not None and end is None:
        end = start + timedelta(days=30)
    if start is None or end is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_PERIOD",
                "message": "统计周期必须包含有效的开始和结束时间",
            },
        )
    try:
        return make_period(start, end)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_PERIOD", "message": str(exc)},
        ) from exc


def _limit(value: int | None, default: int, maximum: int = 100) -> int:
    return min(maximum, max(1, value if value is not None else default))


def _budget(value: int | None) -> int | None:
    if value is not None and value < 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_BUDGET", "message": "预算金额不能为负数"},
        )
    return value


@router.get("/summary", response_model=StatsSummary)
def summary(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    budget_minor: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> StatsSummary:
    return get_summary(db, owner_id, _period(date_from, date_to), _budget(budget_minor))


@router.get("/categories", response_model=CategoryBreakdown)
def categories(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    direction: Literal["expense", "income"] = Query(default="expense"),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> CategoryBreakdown:
    return get_category_breakdown(db, owner_id, _period(date_from, date_to), direction)


@router.get("/trend", response_model=TrendResponse)
def trend(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    granularity: Literal["day", "week", "month", "year"] = Query(default="month"),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> TrendResponse:
    return get_trend(db, owner_id, _period(date_from, date_to), granularity)


@router.get("/merchants", response_model=MerchantRanking)
def merchants(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    direction: Literal["expense", "income"] = Query(default="expense"),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> MerchantRanking:
    return get_top_merchants(
        db,
        owner_id,
        _period(date_from, date_to),
        direction,
        _limit(limit, 10),
    )


@router.get("/large-transactions", response_model=LargeTransactionResponse)
def large_transactions(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    threshold_minor: int = Query(default=10_000, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    direction: Literal["expense", "income"] = Query(default="expense"),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> LargeTransactionResponse:
    return get_large_transactions(
        db,
        owner_id,
        _period(date_from, date_to),
        threshold_minor,
        _limit(limit, 20),
        direction,
    )


@router.get("/fixed-variable", response_model=FixedVariableBreakdown)
def fixed_variable(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> FixedVariableBreakdown:
    return get_fixed_variable(db, owner_id, _period(date_from, date_to))


@router.get("/budget", response_model=BudgetResponse)
def budget(
    budget_minor: int = Query(..., ge=0),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> BudgetResponse:
    period = _period(date_from, date_to)
    result = get_budget_status(db, owner_id, period, budget_minor)
    return BudgetResponse(period=period_response(period), budget=result)


@router.get("/comparison", response_model=ComparisonResponse)
def comparison(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    comparison_from: str | None = Query(default=None, alias="compare_from"),
    comparison_to: str | None = Query(default=None, alias="compare_to"),
    mode: Literal["previous", "yoy"] = Query(default="previous"),
    budget_minor: int | None = Query(default=None, ge=0),
    comparison_budget_minor: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
    owner_id: str = Depends(owner_context),
) -> ComparisonResponse:
    current_period = _period(date_from, date_to)
    if comparison_from or comparison_to:
        comparison_period = _period(comparison_from, comparison_to)
    else:
        comparison_period = None
    return compare_periods(
        db,
        owner_id,
        current_period,
        comparison_period,
        mode,
        _budget(budget_minor),
        _budget(comparison_budget_minor),
    )
