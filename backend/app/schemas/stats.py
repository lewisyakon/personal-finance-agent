from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

StatsGranularity = Literal["day", "week", "month", "year"]


class StatsPeriod(BaseModel):
    start: datetime
    end: datetime
    timezone: str

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("统计时间必须包含时区")
        return value


class BudgetStatus(BaseModel):
    budget_minor: int = Field(ge=0)
    used_minor: int = Field(ge=0)
    remaining_minor: int = Field(ge=0)
    over_budget_minor: int = Field(ge=0)
    utilization_percent: float = Field(ge=0)


class StatsSummary(BaseModel):
    period: StatsPeriod
    currency: str = Field(min_length=3, max_length=3)
    transaction_count: int = Field(ge=0)
    expense_count: int = Field(ge=0)
    income_count: int = Field(ge=0)
    transfer_count: int = Field(ge=0)
    refund_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    expense_minor: int = Field(ge=0)
    income_minor: int = Field(ge=0)
    refund_minor: int = Field(ge=0)
    net_flow_minor: int
    fixed_expense_count: int = Field(ge=0)
    variable_expense_count: int = Field(ge=0)
    fixed_expense_minor: int = Field(ge=0)
    variable_expense_minor: int = Field(ge=0)
    budget: BudgetStatus | None = None


class CategoryBreakdownItem(BaseModel):
    category: str
    primary_category: str
    secondary_category: str | None = None
    amount_minor: int = Field(ge=0)
    transaction_count: int = Field(ge=0)
    share_percent: float = Field(ge=0, le=100)


class CategoryBreakdown(BaseModel):
    period: StatsPeriod
    currency: str = Field(min_length=3, max_length=3)
    direction: Literal["expense", "income"]
    items: list[CategoryBreakdownItem]


class TrendItem(BaseModel):
    bucket_start: datetime
    bucket_end: datetime
    label: str
    transaction_count: int = Field(ge=0)
    expense_count: int = Field(ge=0)
    income_count: int = Field(ge=0)
    transfer_count: int = Field(ge=0)
    refund_count: int = Field(ge=0)
    expense_minor: int = Field(ge=0)
    income_minor: int = Field(ge=0)
    refund_minor: int = Field(ge=0)
    net_flow_minor: int
    fixed_expense_minor: int = Field(ge=0)
    variable_expense_minor: int = Field(ge=0)


class TrendResponse(BaseModel):
    period: StatsPeriod
    currency: str = Field(min_length=3, max_length=3)
    granularity: StatsGranularity
    items: list[TrendItem]


class MerchantRankingItem(BaseModel):
    merchant: str
    amount_minor: int = Field(ge=0)
    transaction_count: int = Field(ge=0)
    share_percent: float = Field(ge=0, le=100)


class MerchantRanking(BaseModel):
    period: StatsPeriod
    currency: str = Field(min_length=3, max_length=3)
    direction: Literal["expense", "income"]
    items: list[MerchantRankingItem]


class LargeTransactionItem(BaseModel):
    id: int
    occurred_at: datetime
    merchant: str
    description: str
    direction: Literal["expense", "income"]
    amount_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    status: str
    category: str | None = None


class LargeTransactionResponse(BaseModel):
    period: StatsPeriod
    currency: str = Field(min_length=3, max_length=3)
    direction: Literal["expense", "income"]
    threshold_minor: int = Field(ge=0)
    items: list[LargeTransactionItem]


class FixedVariableBreakdown(BaseModel):
    period: StatsPeriod
    currency: str = Field(min_length=3, max_length=3)
    fixed_count: int = Field(ge=0)
    variable_count: int = Field(ge=0)
    fixed_minor: int = Field(ge=0)
    variable_minor: int = Field(ge=0)


class ComparisonMetric(BaseModel):
    current: int
    comparison: int
    delta: int
    delta_percent: float | None = None


class ComparisonResponse(BaseModel):
    current: StatsSummary
    comparison: StatsSummary
    comparison_mode: Literal["previous", "yoy"]
    metrics: dict[str, ComparisonMetric]


class BudgetResponse(BaseModel):
    period: StatsPeriod
    budget: BudgetStatus
