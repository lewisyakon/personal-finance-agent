"""Strict public contracts for the stage 4 read-only Tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.stats import StatsPeriod

ToolStatus = Literal["success", "error"]
Direction = Literal["expense", "income"]
TransactionDirection = Literal["expense", "income", "transfer", "unknown"]
TransactionStatus = Literal["success", "failed", "refunded", "pending", "unknown"]
Granularity = Literal["day", "week", "month", "year"]


class OwnerContext(BaseModel):
    """Trusted runtime context; it is never part of a model-provided Tool input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: str = Field(min_length=1, max_length=128)


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PeriodArguments(ToolArguments):
    date_from: datetime = Field(alias="from")
    date_to: datetime = Field(alias="to")

    @field_validator("date_from", "date_to")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("日期时间必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_period(self) -> PeriodArguments:
        if self.date_to <= self.date_from:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class SpendingSummaryArguments(PeriodArguments):
    budget_minor: int | None = Field(default=None, ge=0, strict=True)


class CategoryBreakdownArguments(PeriodArguments):
    direction: Direction = "expense"


class TrendArguments(PeriodArguments):
    granularity: Granularity = "month"

    @model_validator(mode="after")
    def bound_bucket_count(self) -> TrendArguments:
        duration_days = (self.date_to - self.date_from).total_seconds() / 86_400
        maximum_days = {
            "day": 400,
            "week": 2_800,
            "month": 12_400,
            "year": 146_400,
        }[self.granularity]
        if duration_days > maximum_days:
            raise ValueError("趋势周期最多返回约 400 个时间桶")
        return self


class TopMerchantsArguments(PeriodArguments):
    direction: Direction = "expense"
    limit: int = Field(default=10, ge=1, le=100, strict=True)


class LargeTransactionsArguments(PeriodArguments):
    direction: Direction = "expense"
    threshold_minor: int = Field(default=10_000, ge=0, strict=True)
    limit: int = Field(default=20, ge=1, le=100, strict=True)


class SearchTransactionsArguments(PeriodArguments):
    direction: TransactionDirection | None = None
    status: TransactionStatus | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    merchant: str | None = Field(default=None, min_length=1, max_length=120)
    search: str | None = Field(default=None, min_length=1, max_length=120)
    min_amount_minor: int | None = Field(default=None, ge=0, strict=True)
    max_amount_minor: int | None = Field(default=None, ge=0, strict=True)
    page: int = Field(default=1, ge=1, le=10_000, strict=True)
    page_size: int = Field(default=20, ge=1, le=50, strict=True)

    @field_validator("category", "merchant", "search", mode="before")
    @classmethod
    def strip_filters(cls, value: str | None) -> str | None:
        if value is None or not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("筛选文本不能为空")
        return stripped

    @model_validator(mode="after")
    def validate_amount_range(self) -> SearchTransactionsArguments:
        if (
            self.min_amount_minor is not None
            and self.max_amount_minor is not None
            and self.min_amount_minor > self.max_amount_minor
        ):
            raise ValueError("最小金额不能大于最大金额")
        return self


class ComparePeriodsArguments(PeriodArguments):
    comparison_from: datetime = Field(alias="compare_from")
    comparison_to: datetime = Field(alias="compare_to")
    mode: Literal["previous", "yoy"] = "previous"
    current_budget_minor: int | None = Field(default=None, ge=0, strict=True)
    comparison_budget_minor: int | None = Field(default=None, ge=0, strict=True)

    @field_validator("comparison_from", "comparison_to")
    @classmethod
    def require_comparison_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("比较日期时间必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_comparison_period(self) -> ComparePeriodsArguments:
        if self.comparison_to <= self.comparison_from:
            raise ValueError("比较周期结束时间必须晚于开始时间")
        return self


class BudgetStatusArguments(PeriodArguments):
    budget_minor: int = Field(ge=0, strict=True)


class MerchantHistoryArguments(PeriodArguments):
    merchant: str = Field(min_length=1, max_length=120)
    page: int = Field(default=1, ge=1, le=10_000, strict=True)
    page_size: int = Field(default=20, ge=1, le=50, strict=True)

    @field_validator("merchant", mode="before")
    @classmethod
    def strip_merchant(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("商户名称不能为空")
        return stripped


class ToolError(BaseModel):
    code: str
    message: str
    details: list[dict[str, str]] = Field(default_factory=list)


class ToolMethodology(BaseModel):
    source_service: Literal["stats_service", "transaction_service"]
    period_semantics: str = "[from, to)"
    timezone: str
    amount_unit: str = "integer_minor_currency_unit"
    notes: list[str] = Field(default_factory=list)


class ToolExecutionResult(BaseModel):
    evidence_id: str
    tool_name: str
    contract_version: str = "1.0"
    status: ToolStatus
    data: dict[str, Any] | None = None
    methodology: ToolMethodology | None = None
    error: ToolError | None = None
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    replayed: bool = False


class ToolTransactionItem(BaseModel):
    id: int
    occurred_at: datetime
    direction: str
    amount_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    status: str
    merchant: str
    description_excerpt: str
    category: str | None = None


class SearchTransactionsResult(BaseModel):
    period: StatsPeriod
    items: list[ToolTransactionItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)


class MerchantCurrencyTotals(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    expense_minor: int = Field(ge=0)
    income_minor: int = Field(ge=0)
    transfer_count: int = Field(ge=0)


class MerchantCategoryCount(BaseModel):
    category: str
    transaction_count: int = Field(ge=0)


class MerchantHistoryResult(BaseModel):
    merchant: str
    period: StatsPeriod
    transaction_count: int = Field(ge=0)
    user_correction_count: int = Field(ge=0)
    user_corrections: list[MerchantCategoryCount]
    totals: list[MerchantCurrencyTotals]
    categories: list[MerchantCategoryCount]
    items: list[ToolTransactionItem]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)
