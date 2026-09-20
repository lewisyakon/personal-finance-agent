"""Deterministic, bounded transaction queries used by read-only Tools."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.finance import Transaction, TransactionCategoryChange
from app.schemas.imports import TransactionResponse
from app.services.import_service import list_transactions
from app.services.stats_service import Period, period_response
from app.tools.contracts import (
    MerchantCategoryCount,
    MerchantCurrencyTotals,
    MerchantHistoryResult,
    SearchTransactionsArguments,
    SearchTransactionsResult,
    ToolTransactionItem,
)

_VALID_STATUSES = ("success", "refunded")


def _tool_item(item: TransactionResponse | Transaction) -> ToolTransactionItem:
    category = item.category or item.platform_category or None
    return ToolTransactionItem(
        id=item.id,
        occurred_at=item.occurred_at,
        direction=item.direction,
        amount_minor=item.amount_minor,
        currency=(item.currency or "CNY").upper(),
        status=item.status,
        merchant=item.merchant or item.description or "未知商户",
        # Tool traces intentionally keep only a bounded excerpt, not a full
        # source row or platform transaction identifier.
        description_excerpt=(item.description or "")[:160],
        category=category,
    )


def search_transactions(
    db: Session,
    owner_id: str,
    period: Period,
    arguments: SearchTransactionsArguments,
) -> SearchTransactionsResult:
    result = list_transactions(
        db,
        owner_id,
        arguments.page,
        arguments.page_size,
        date_from=period.start_utc_naive,
        date_to=period.end_utc_naive,
        direction=arguments.direction,
        status=arguments.status,
        category=arguments.category,
        merchant=arguments.merchant,
        search=arguments.search,
        min_amount=arguments.min_amount_minor,
        max_amount=arguments.max_amount_minor,
    )
    return SearchTransactionsResult(
        period=period_response(period),
        items=[_tool_item(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


def _merchant_predicates(owner_id: str, period: Period, merchant: str) -> Sequence:
    return (
        Transaction.owner_id == owner_id,
        Transaction.occurred_at >= period.start_utc_naive,
        Transaction.occurred_at < period.end_utc_naive,
        func.lower(func.trim(Transaction.merchant)) == merchant.casefold(),
    )


def get_merchant_history(
    db: Session,
    owner_id: str,
    period: Period,
    merchant: str,
    page: int,
    page_size: int,
) -> MerchantHistoryResult:
    predicates = _merchant_predicates(owner_id, period, merchant)
    total = db.scalar(select(func.count()).select_from(Transaction).where(*predicates)) or 0

    query = (
        select(Transaction)
        .where(*predicates)
        .order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(query))

    valid = Transaction.status.in_(_VALID_STATUSES)
    totals_query = (
        select(
            Transaction.currency,
            func.sum(
                case(
                    (valid & (Transaction.direction == "expense"), Transaction.amount_minor),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (valid & (Transaction.direction == "income"), Transaction.amount_minor),
                    else_=0,
                )
            ),
            func.sum(case((valid & (Transaction.direction == "transfer"), 1), else_=0)),
        )
        .where(*predicates)
        .group_by(Transaction.currency)
        .order_by(Transaction.currency)
    )
    totals = [
        MerchantCurrencyTotals(
            currency=(currency or "CNY").upper(),
            expense_minor=expense_minor or 0,
            income_minor=income_minor or 0,
            transfer_count=transfer_count or 0,
        )
        for currency, expense_minor, income_minor, transfer_count in db.execute(totals_query)
    ]

    effective_category = func.coalesce(
        func.nullif(func.trim(Transaction.category), ""),
        func.nullif(func.trim(Transaction.platform_category), ""),
        "未分类",
    )
    category_rows = db.execute(
        select(effective_category, func.count())
        .where(*predicates)
        .group_by(effective_category)
        .order_by(func.count().desc(), effective_category)
        .limit(100)
    )
    categories = [
        MerchantCategoryCount(category=category, transaction_count=count)
        for category, count in category_rows
    ]

    corrected_category = func.coalesce(TransactionCategoryChange.new_category, "未分类")
    correction_rows = list(
        db.execute(
            select(corrected_category, func.count())
            .select_from(TransactionCategoryChange)
            .join(Transaction, Transaction.id == TransactionCategoryChange.transaction_id)
            .where(
                TransactionCategoryChange.owner_id == owner_id,
                *predicates,
                TransactionCategoryChange.source == "user",
            )
            .group_by(corrected_category)
            .order_by(func.count().desc(), corrected_category)
            .limit(100)
        )
    )
    user_corrections = [
        MerchantCategoryCount(category=category, transaction_count=count)
        for category, count in correction_rows
    ]
    correction_count = (
        db.scalar(
            select(func.count())
            .select_from(TransactionCategoryChange)
            .join(Transaction, Transaction.id == TransactionCategoryChange.transaction_id)
            .where(
                TransactionCategoryChange.owner_id == owner_id,
                *predicates,
                TransactionCategoryChange.source == "user",
            )
        )
        or 0
    )

    return MerchantHistoryResult(
        merchant=merchant,
        period=period_response(period),
        transaction_count=total,
        user_correction_count=correction_count,
        user_corrections=user_corrections,
        totals=totals,
        categories=categories,
        items=[_tool_item(item) for item in items],
        page=page,
        page_size=page_size,
    )
