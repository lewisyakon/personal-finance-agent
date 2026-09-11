"""Deterministic statistics over normalized transactions.

All monetary values are integer minor currency units.  This module is the
single source of truth for the statistics API and the future read-only tools.
It deliberately performs no model calls and never accepts an arbitrary SQL
fragment from callers.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.finance import Transaction
from app.schemas.stats import (
    BudgetStatus,
    CategoryBreakdown,
    CategoryBreakdownItem,
    ComparisonMetric,
    ComparisonResponse,
    FixedVariableBreakdown,
    LargeTransactionItem,
    LargeTransactionResponse,
    MerchantRanking,
    MerchantRankingItem,
    StatsPeriod,
    StatsSummary,
    TrendItem,
    TrendResponse,
)

StatsDirection = Literal["expense", "income"]
StatsGranularity = Literal["day", "week", "month", "year"]

_VALID_STATUSES = {"success", "refunded"}
_FIXED_KEYWORDS = (
    "房租",
    "租金",
    "房贷",
    "贷款",
    "水费",
    "电费",
    "燃气",
    "物业",
    "宽带",
    "手机",
    "话费",
    "保险",
    "社保",
    "公积金",
    "学费",
    "订阅",
    "会员",
    "subscription",
    "rent",
    "mortgage",
    "insurance",
    "utility",
)
_CATEGORY_SEPARATOR = re.compile(r"\s*(?:/|／|>|＞|\\|\||｜|::|：)\s*")


class StatsServiceError(ValueError):
    """A safe, user-facing validation error raised by deterministic statistics."""


@dataclass(frozen=True)
class Period:
    """An inclusive-start, exclusive-end period in the configured timezone."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("统计周期必须包含时区")
        if self.end <= self.start:
            raise ValueError("统计周期结束时间必须晚于开始时间")

    @property
    def start_utc_naive(self) -> datetime:
        return self.start.astimezone(UTC).replace(tzinfo=None)

    @property
    def end_utc_naive(self) -> datetime:
        return self.end.astimezone(UTC).replace(tzinfo=None)


def default_period(now: datetime | None = None) -> Period:
    timezone = ZoneInfo(get_settings().app_timezone)
    current = now or datetime.now(timezone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone)
    else:
        current = current.astimezone(timezone)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0, day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return Period(start, end)


def make_period(start: datetime, end: datetime) -> Period:
    timezone = ZoneInfo(get_settings().app_timezone)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone)
    return Period(start.astimezone(timezone), end.astimezone(timezone))


def shift_period(period: Period, mode: Literal["previous", "yoy"]) -> Period:
    if mode == "previous":
        duration = period.end - period.start
        return Period(period.start - duration, period.end - duration)
    if mode != "yoy":
        raise StatsServiceError("不支持的比较模式")
    start = _shift_year(period.start, -1)
    end = _shift_year(period.end, -1)
    return Period(start, end)


def _shift_year(value: datetime, years: int) -> datetime:
    year = value.year + years
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return value.replace(year=year, day=day)


def period_response(period: Period) -> StatsPeriod:
    return StatsPeriod(
        start=period.start,
        end=period.end,
        timezone=get_settings().app_timezone,
    )


def _load_transactions(db: Session, owner_id: str, period: Period) -> list[Transaction]:
    query = (
        select(Transaction)
        .where(
            Transaction.owner_id == owner_id,
            Transaction.occurred_at >= period.start_utc_naive,
            Transaction.occurred_at < period.end_utc_naive,
        )
        .order_by(Transaction.occurred_at.asc(), Transaction.id.asc())
    )
    return list(db.scalars(query))


def _effective_kind(item: Transaction) -> str:
    """Return expense, income, transfer, or excluded for aggregation."""

    if item.status not in _VALID_STATUSES:
        return "excluded"
    # WeChat commonly exports a refunded expense row together with a separate
    # refund receipt row.  Preserve the original expense direction and count
    # only the receipt row as refund income; otherwise the original purchase
    # would disappear from spending and the refund could be double-counted.
    if item.status == "refunded":
        if item.direction in {"expense", "income", "transfer"}:
            return item.direction
        return "excluded"
    if item.direction == "transfer":
        return "transfer"
    if item.direction in {"expense", "income"}:
        return item.direction
    return "excluded"


def _is_refund(item: Transaction) -> bool:
    return item.status == "refunded" and item.direction == "income"


def _validate_direction(direction: str) -> StatsDirection:
    if direction not in {"expense", "income"}:
        raise StatsServiceError("方向必须是 expense 或 income")
    return cast(StatsDirection, direction)


def _validate_granularity(granularity: str) -> StatsGranularity:
    if granularity not in {"day", "week", "month", "year"}:
        raise StatsServiceError("统计粒度必须是 day、week、month 或 year")
    return cast(StatsGranularity, granularity)


def _category_parts(item: Transaction) -> tuple[str, str | None]:
    raw = (item.category or item.platform_category or "").strip()
    if not raw:
        return "未分类", None
    parts = [part.strip() for part in _CATEGORY_SEPARATOR.split(raw, maxsplit=1)]
    primary = parts[0] or "未分类"
    secondary = parts[1] if len(parts) > 1 and parts[1] else None
    return primary, secondary


def _merchant_name(item: Transaction) -> str:
    return (item.merchant or item.description or "未知商户").strip() or "未知商户"


def _is_fixed(item: Transaction) -> bool:
    primary, secondary = _category_parts(item)
    haystack = " ".join(
        value.lower()
        for value in (primary, secondary or "", item.merchant or "", item.description or "")
    )
    return any(keyword in haystack for keyword in _FIXED_KEYWORDS)


def _currency(transactions: Iterable[Transaction]) -> str:
    currencies = {
        (item.currency or "CNY").upper()
        for item in transactions
        if _effective_kind(item) != "excluded"
    }
    if not currencies:
        return "CNY"
    if len(currencies) > 1:
        names = ", ".join(sorted(currencies))
        raise StatsServiceError(f"统计周期包含多个币种（{names}），请分别统计")
    return next(iter(currencies))


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator * 100 / denominator, 2)


def _summary_from_transactions(
    transactions: Iterable[Transaction],
    period: Period,
    budget_minor: int | None = None,
) -> StatsSummary:
    transactions = list(transactions)
    expense_minor = income_minor = refund_minor = 0
    expense_count = income_count = transfer_count = refund_count = excluded_count = 0
    fixed_expense_minor = variable_expense_minor = 0
    fixed_expense_count = variable_expense_count = 0

    for item in transactions:
        kind = _effective_kind(item)
        if kind == "excluded":
            excluded_count += 1
            continue
        if kind == "transfer":
            transfer_count += 1
            continue
        if kind == "expense":
            expense_count += 1
            expense_minor += item.amount_minor
            if _is_fixed(item):
                fixed_expense_count += 1
                fixed_expense_minor += item.amount_minor
            else:
                variable_expense_count += 1
                variable_expense_minor += item.amount_minor
            continue
        income_count += 1
        income_minor += item.amount_minor
        if _is_refund(item):
            refund_count += 1
            refund_minor += item.amount_minor

    budget = None
    if budget_minor is not None:
        used = expense_minor
        budget = BudgetStatus(
            budget_minor=budget_minor,
            used_minor=used,
            remaining_minor=max(0, budget_minor - used),
            over_budget_minor=max(0, used - budget_minor),
            utilization_percent=round(used * 100 / budget_minor, 2) if budget_minor else 0.0,
        )

    return StatsSummary(
        period=period_response(period),
        currency=_currency(transactions),
        transaction_count=expense_count + income_count + transfer_count,
        expense_count=expense_count,
        income_count=income_count,
        transfer_count=transfer_count,
        refund_count=refund_count,
        excluded_count=excluded_count,
        expense_minor=expense_minor,
        income_minor=income_minor,
        refund_minor=refund_minor,
        net_flow_minor=income_minor - expense_minor,
        fixed_expense_count=fixed_expense_count,
        variable_expense_count=variable_expense_count,
        fixed_expense_minor=fixed_expense_minor,
        variable_expense_minor=variable_expense_minor,
        budget=budget,
    )


def get_summary(
    db: Session,
    owner_id: str,
    period: Period,
    budget_minor: int | None = None,
) -> StatsSummary:
    transactions = _load_transactions(db, owner_id, period)
    return _summary_from_transactions(transactions, period, budget_minor)


def get_spending_summary(
    db: Session,
    owner_id: str,
    period: Period,
    budget_minor: int | None = None,
) -> StatsSummary:
    """Descriptive alias used by the future read-only statistics tool."""

    return get_summary(db, owner_id, period, budget_minor)


def get_category_breakdown(
    db: Session,
    owner_id: str,
    period: Period,
    direction: StatsDirection = "expense",
) -> CategoryBreakdown:
    direction = _validate_direction(direction)
    transactions = _load_transactions(db, owner_id, period)
    grouped: dict[tuple[str, str | None], list[int]] = defaultdict(lambda: [0, 0])
    for item in transactions:
        if _effective_kind(item) != direction:
            continue
        primary, secondary = _category_parts(item)
        grouped[(primary, secondary)][0] += item.amount_minor
        grouped[(primary, secondary)][1] += 1
    total = sum(values[0] for values in grouped.values())
    items = [
        CategoryBreakdownItem(
            category=primary if secondary is None else f"{primary}/{secondary}",
            primary_category=primary,
            secondary_category=secondary,
            amount_minor=values[0],
            transaction_count=values[1],
            share_percent=_percent(values[0], total),
        )
        for (primary, secondary), values in grouped.items()
    ]
    items.sort(key=lambda item: (-item.amount_minor, item.category))
    return CategoryBreakdown(
        period=period_response(period),
        currency=_currency(transactions),
        direction=direction,
        items=items,
    )


def _bucket_start(value: datetime, granularity: str) -> datetime:
    value = value.replace(microsecond=0)
    if granularity == "day":
        return value.replace(hour=0, minute=0, second=0)
    if granularity == "week":
        day_start = value.replace(hour=0, minute=0, second=0)
        return day_start - timedelta(days=day_start.weekday())
    if granularity == "month":
        return value.replace(day=1, hour=0, minute=0, second=0)
    if granularity == "year":
        return value.replace(month=1, day=1, hour=0, minute=0, second=0)
    raise ValueError("不支持的统计粒度")


def _next_bucket(value: datetime, granularity: str) -> datetime:
    if granularity == "day":
        return value + timedelta(days=1)
    if granularity == "week":
        return value + timedelta(days=7)
    if granularity == "month":
        if value.month == 12:
            return value.replace(year=value.year + 1, month=1)
        return value.replace(month=value.month + 1)
    if granularity == "year":
        return value.replace(year=value.year + 1)
    raise ValueError("不支持的统计粒度")


def _bucket_label(value: datetime, granularity: str) -> str:
    if granularity == "day":
        return value.strftime("%Y-%m-%d")
    if granularity == "week":
        return f"{value.strftime('%Y-%m-%d')} 周"
    if granularity == "month":
        return value.strftime("%Y-%m")
    return value.strftime("%Y")


def _trend_accumulator() -> dict[str, int]:
    return {
        "transaction_count": 0,
        "expense_count": 0,
        "income_count": 0,
        "transfer_count": 0,
        "refund_count": 0,
        "expense_minor": 0,
        "income_minor": 0,
        "refund_minor": 0,
        "fixed_expense_minor": 0,
        "variable_expense_minor": 0,
    }


def get_trend(
    db: Session,
    owner_id: str,
    period: Period,
    granularity: StatsGranularity = "month",
) -> TrendResponse:
    granularity = _validate_granularity(granularity)
    transactions = _load_transactions(db, owner_id, period)
    timezone = ZoneInfo(get_settings().app_timezone)
    first_bucket = _bucket_start(period.start, granularity)
    buckets: dict[datetime, dict[str, int]] = {}
    cursor = first_bucket
    while cursor < period.end:
        buckets[cursor] = _trend_accumulator()
        cursor = _next_bucket(cursor, granularity)

    for item in transactions:
        occurred_at = item.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        local_time = occurred_at.astimezone(timezone)
        start = _bucket_start(local_time, granularity)
        accumulator = buckets.setdefault(start, _trend_accumulator())
        kind = _effective_kind(item)
        if kind == "excluded":
            continue
        accumulator["transaction_count"] += 1
        if kind == "transfer":
            accumulator["transfer_count"] += 1
        elif kind == "expense":
            accumulator["expense_count"] += 1
            accumulator["expense_minor"] += item.amount_minor
            if _is_fixed(item):
                accumulator["fixed_expense_minor"] += item.amount_minor
            else:
                accumulator["variable_expense_minor"] += item.amount_minor
        elif kind == "income":
            accumulator["income_count"] += 1
            accumulator["income_minor"] += item.amount_minor
            if _is_refund(item):
                accumulator["refund_count"] += 1
                accumulator["refund_minor"] += item.amount_minor

    items: list[TrendItem] = []
    for start, values in sorted(buckets.items()):
        end = _next_bucket(start, granularity)
        items.append(
            TrendItem(
                bucket_start=max(start, period.start),
                bucket_end=min(end, period.end),
                label=_bucket_label(start, granularity),
                **values,
                net_flow_minor=values["income_minor"] - values["expense_minor"],
            )
        )
    return TrendResponse(
        period=period_response(period),
        currency=_currency(transactions),
        granularity=granularity,
        items=items,
    )


def get_top_merchants(
    db: Session,
    owner_id: str,
    period: Period,
    direction: StatsDirection = "expense",
    limit: int = 10,
) -> MerchantRanking:
    direction = _validate_direction(direction)
    if limit < 1:
        raise StatsServiceError("商户排行数量上限必须大于 0")
    limit = min(limit, 100)
    transactions = _load_transactions(db, owner_id, period)
    grouped: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item in transactions:
        if _effective_kind(item) != direction:
            continue
        merchant = _merchant_name(item)
        grouped[merchant][0] += item.amount_minor
        grouped[merchant][1] += 1
    total = sum(values[0] for values in grouped.values())
    items = [
        MerchantRankingItem(
            merchant=merchant,
            amount_minor=values[0],
            transaction_count=values[1],
            share_percent=_percent(values[0], total),
        )
        for merchant, values in grouped.items()
    ]
    items.sort(key=lambda item: (-item.amount_minor, item.merchant))
    return MerchantRanking(
        period=period_response(period),
        currency=_currency(transactions),
        direction=direction,
        items=items[:limit],
    )


def get_large_transactions(
    db: Session,
    owner_id: str,
    period: Period,
    threshold_minor: int = 10_000,
    limit: int = 20,
    direction: StatsDirection = "expense",
) -> LargeTransactionResponse:
    direction = _validate_direction(direction)
    transactions = _load_transactions(db, owner_id, period)
    if threshold_minor < 0:
        raise StatsServiceError("大额交易阈值不能为负数")
    if limit < 1:
        raise StatsServiceError("大额交易数量上限必须大于 0")
    limit = min(limit, 100)
    items = [
        LargeTransactionItem(
            id=item.id,
            occurred_at=(
                item.occurred_at
                if item.occurred_at.tzinfo is not None
                else item.occurred_at.replace(tzinfo=UTC)
            ).astimezone(UTC),
            merchant=_merchant_name(item),
            description=item.description,
            direction=direction,
            amount_minor=item.amount_minor,
            currency=(item.currency or "CNY").upper(),
            status=item.status,
            category=(item.category or item.platform_category or None),
        )
        for item in transactions
        if _effective_kind(item) == direction and item.amount_minor >= threshold_minor
    ]
    items.sort(key=lambda item: (-item.amount_minor, item.occurred_at, item.id))
    return LargeTransactionResponse(
        period=period_response(period),
        currency=_currency(transactions),
        direction=direction,
        threshold_minor=threshold_minor,
        items=items[:limit],
    )


def get_fixed_variable(
    db: Session,
    owner_id: str,
    period: Period,
) -> FixedVariableBreakdown:
    summary = get_summary(db, owner_id, period)
    return FixedVariableBreakdown(
        period=summary.period,
        currency=summary.currency,
        fixed_count=summary.fixed_expense_count,
        variable_count=summary.variable_expense_count,
        fixed_minor=summary.fixed_expense_minor,
        variable_minor=summary.variable_expense_minor,
    )


def get_budget_status(
    db: Session,
    owner_id: str,
    period: Period,
    budget_minor: int,
) -> BudgetStatus:
    if budget_minor < 0:
        raise StatsServiceError("预算金额不能为负数")
    summary = get_summary(db, owner_id, period, budget_minor=budget_minor)
    if summary.budget is None:
        raise RuntimeError("预算统计生成失败")
    return summary.budget


def compare_periods(
    db: Session,
    owner_id: str,
    current_period: Period,
    comparison_period: Period | None = None,
    mode: Literal["previous", "yoy"] = "previous",
    current_budget_minor: int | None = None,
    comparison_budget_minor: int | None = None,
) -> ComparisonResponse:
    if mode not in {"previous", "yoy"}:
        raise StatsServiceError("不支持的比较模式")
    comparison_period = comparison_period or shift_period(current_period, mode)
    current = get_summary(db, owner_id, current_period, current_budget_minor)
    comparison = get_summary(db, owner_id, comparison_period, comparison_budget_minor)
    if current.currency != comparison.currency:
        raise StatsServiceError("比较周期的币种不一致，不能直接比较")

    def metric(
        name: str, current_value: int, comparison_value: int
    ) -> tuple[str, ComparisonMetric]:
        delta = current_value - comparison_value
        percent = None if comparison_value == 0 else round(delta * 100 / comparison_value, 2)
        return name, ComparisonMetric(
            current=current_value,
            comparison=comparison_value,
            delta=delta,
            delta_percent=percent,
        )

    metrics = dict(
        [
            metric("expense_minor", current.expense_minor, comparison.expense_minor),
            metric("income_minor", current.income_minor, comparison.income_minor),
            metric("net_flow_minor", current.net_flow_minor, comparison.net_flow_minor),
            metric("transaction_count", current.transaction_count, comparison.transaction_count),
            metric("refund_minor", current.refund_minor, comparison.refund_minor),
            metric("expense_count", current.expense_count, comparison.expense_count),
            metric("income_count", current.income_count, comparison.income_count),
            metric(
                "fixed_expense_minor",
                current.fixed_expense_minor,
                comparison.fixed_expense_minor,
            ),
            metric(
                "variable_expense_minor",
                current.variable_expense_minor,
                comparison.variable_expense_minor,
            ),
        ]
    )
    return ComparisonResponse(
        current=current,
        comparison=comparison,
        comparison_mode=mode,
        metrics=metrics,
    )
