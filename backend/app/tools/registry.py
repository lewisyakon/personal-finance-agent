"""Registry and deterministic handlers for the first read-only Tool set."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.stats import BudgetResponse
from app.services.stats_service import (
    compare_periods,
    get_budget_status,
    get_category_breakdown,
    get_large_transactions,
    get_spending_summary,
    get_top_merchants,
    get_trend,
    make_period,
    period_response,
)
from app.services.tool_query_service import (
    get_merchant_history as query_merchant_history,
)
from app.services.tool_query_service import (
    search_transactions as query_transactions,
)
from app.tools.contracts import (
    BudgetStatusArguments,
    CategoryBreakdownArguments,
    ComparePeriodsArguments,
    LargeTransactionsArguments,
    MerchantHistoryArguments,
    OwnerContext,
    PeriodArguments,
    SearchTransactionsArguments,
    SpendingSummaryArguments,
    ToolArguments,
    ToolMethodology,
    TopMerchantsArguments,
    TrendArguments,
)

ToolHandler = Callable[[Session, OwnerContext, ToolArguments], BaseModel | dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments_model: type[ToolArguments]
    handler: ToolHandler
    source_service: Literal["stats_service", "transaction_service"]
    notes: tuple[str, ...] = ()
    contract_version: str = "1.0"

    def methodology(self) -> ToolMethodology:
        return ToolMethodology(
            source_service=self.source_service,
            timezone=get_settings().app_timezone,
            notes=list(self.notes),
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Tool 已注册: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._definitions[name] for name in sorted(self._definitions))

    def model_tool_schemas(self) -> list[dict[str, Any]]:
        """Return provider-neutral function schemas; owner_id is never present."""

        return [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.arguments_model.model_json_schema(by_alias=True),
                },
            }
            for definition in self.definitions()
        ]


def _period(arguments: PeriodArguments):
    return make_period(arguments.date_from, arguments.date_to)


def _spending_summary(db: Session, context: OwnerContext, raw: ToolArguments) -> BaseModel:
    arguments = cast(SpendingSummaryArguments, raw)
    return get_spending_summary(
        db,
        context.owner_id,
        _period(arguments),
        arguments.budget_minor,
    )


def _category_breakdown(db: Session, context: OwnerContext, raw: ToolArguments) -> BaseModel:
    arguments = cast(CategoryBreakdownArguments, raw)
    return get_category_breakdown(
        db,
        context.owner_id,
        _period(arguments),
        arguments.direction,
    )


def _trend(db: Session, context: OwnerContext, raw: ToolArguments) -> BaseModel:
    arguments = cast(TrendArguments, raw)
    return get_trend(
        db,
        context.owner_id,
        _period(arguments),
        arguments.granularity,
    )


def _top_merchants(db: Session, context: OwnerContext, raw: ToolArguments) -> BaseModel:
    arguments = cast(TopMerchantsArguments, raw)
    return get_top_merchants(
        db,
        context.owner_id,
        _period(arguments),
        arguments.direction,
        arguments.limit,
    )


def _large_transactions(db: Session, context: OwnerContext, raw: ToolArguments) -> BaseModel:
    arguments = cast(LargeTransactionsArguments, raw)
    return get_large_transactions(
        db,
        context.owner_id,
        _period(arguments),
        arguments.threshold_minor,
        arguments.limit,
        arguments.direction,
    )


def _search_transactions(db: Session, context: OwnerContext, raw: ToolArguments) -> BaseModel:
    arguments = cast(SearchTransactionsArguments, raw)
    return query_transactions(db, context.owner_id, _period(arguments), arguments)


def _compare_periods(db: Session, context: OwnerContext, raw: ToolArguments) -> BaseModel:
    arguments = cast(ComparePeriodsArguments, raw)
    return compare_periods(
        db,
        context.owner_id,
        _period(arguments),
        make_period(arguments.comparison_from, arguments.comparison_to),
        arguments.mode,
        arguments.current_budget_minor,
        arguments.comparison_budget_minor,
    )


def _budget_status(db: Session, context: OwnerContext, raw: ToolArguments) -> BaseModel:
    arguments = cast(BudgetStatusArguments, raw)
    period = _period(arguments)
    return BudgetResponse(
        period=period_response(period),
        budget=get_budget_status(db, context.owner_id, period, arguments.budget_minor),
    )


def _merchant_history(db: Session, context: OwnerContext, raw: ToolArguments) -> BaseModel:
    arguments = cast(MerchantHistoryArguments, raw)
    return query_merchant_history(
        db,
        context.owner_id,
        _period(arguments),
        arguments.merchant,
        arguments.page,
        arguments.page_size,
    )


def build_readonly_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    common_stats_notes = (
        "退款、转账、失败交易和币种按阶段 3 统计口径处理",
        "金额由确定性 Stats Service 计算，模型不得重新汇总",
    )
    definitions = (
        ToolDefinition(
            "get_spending_summary",
            "获取明确周期内的收支、净流量、退款、交易数量及固定/可变支出汇总。",
            SpendingSummaryArguments,
            _spending_summary,
            "stats_service",
            common_stats_notes,
        ),
        ToolDefinition(
            "get_category_breakdown",
            "获取明确周期内指定收支方向的分类构成。",
            CategoryBreakdownArguments,
            _category_breakdown,
            "stats_service",
            common_stats_notes,
        ),
        ToolDefinition(
            "get_trend",
            "获取明确周期内按日、周、月或年分桶的收支趋势。",
            TrendArguments,
            _trend,
            "stats_service",
            common_stats_notes,
        ),
        ToolDefinition(
            "get_top_merchants",
            "获取明确周期内指定收支方向的主要商户排行。",
            TopMerchantsArguments,
            _top_merchants,
            "stats_service",
            common_stats_notes,
        ),
        ToolDefinition(
            "get_large_transactions",
            "获取明确周期内达到阈值的大额收入或支出，结果数量受限。",
            LargeTransactionsArguments,
            _large_transactions,
            "stats_service",
            common_stats_notes,
        ),
        ToolDefinition(
            "search_transactions",
            "按明确周期和受控筛选条件分页搜索交易，不接受 SQL。",
            SearchTransactionsArguments,
            _search_transactions,
            "transaction_service",
            ("结果分页且每页最多 50 条", "描述只保留最多 160 个字符的摘要"),
        ),
        ToolDefinition(
            "compare_periods",
            "比较两个明确周期的收支、净流量、交易数量和固定/可变支出。",
            ComparePeriodsArguments,
            _compare_periods,
            "stats_service",
            common_stats_notes,
        ),
        ToolDefinition(
            "get_budget_status",
            "按明确周期和整数最小货币单位预算计算已用、剩余与超支。",
            BudgetStatusArguments,
            _budget_status,
            "stats_service",
            common_stats_notes,
        ),
        ToolDefinition(
            "get_merchant_history",
            "获取一个明确商户在指定周期内的分页交易、分类和用户修正历史。",
            MerchantHistoryArguments,
            _merchant_history,
            "transaction_service",
            ("商户名称使用去除首尾空格后的精确匹配", "金额按币种分别汇总"),
        ),
    )
    for definition in definitions:
        registry.register(definition)
    return registry


readonly_tool_registry = build_readonly_tool_registry()
