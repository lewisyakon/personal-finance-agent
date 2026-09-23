from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.finance import BillImport, Transaction, WorkspaceOwner
from app.services.import_service import update_category
from app.services.stats_service import (
    StatsServiceError,
    compare_periods,
    get_budget_status,
    get_category_breakdown,
    get_fixed_variable,
    get_large_transactions,
    get_summary,
    get_top_merchants,
    get_trend,
    make_period,
)

TZ = ZoneInfo("Asia/Shanghai")


def _at(day: int, hour: int = 12, minute: int = 0, year: int = 2026, month: int = 1):
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


def _database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stats.db'}", future=True)
    Base.metadata.create_all(engine)
    return engine


def _seed(engine):
    with Session(engine) as db:
        owner_a = WorkspaceOwner(id="owner-a", display_name="测试用户 A")
        owner_b = WorkspaceOwner(id="owner-b", display_name="测试用户 B")
        bill_a = BillImport(
            id="import-a",
            owner_id="owner-a",
            file_name="synthetic.csv",
            file_sha256="a" * 64,
            status="completed",
        )
        bill_b = BillImport(
            id="import-b",
            owner_id="owner-b",
            file_name="synthetic.csv",
            file_sha256="b" * 64,
            status="completed",
        )
        db.add_all([owner_a, owner_b, bill_a, bill_b])

        def add(
            *,
            owner_id: str = "owner-a",
            bill_import_id: str = "import-a",
            occurred_at: datetime,
            amount_minor: int,
            direction: str,
            status: str = "success",
            merchant: str = "",
            description: str = "",
            platform_category: str = "",
            category: str | None = None,
            source_row: int,
        ) -> None:
            db.add(
                Transaction(
                    owner_id=owner_id,
                    bill_import_id=bill_import_id,
                    fingerprint=f"{owner_id}-{source_row}",
                    platform="wechat",
                    occurred_at=occurred_at,
                    direction=direction,
                    amount_minor=amount_minor,
                    currency="CNY",
                    status=status,
                    merchant=merchant,
                    description=description,
                    payment_method="零钱",
                    platform_category=platform_category,
                    category=category,
                    source_row=source_row,
                )
            )

        # Current period: 2026-01-01 (inclusive) through 2026-02-01 (exclusive).
        add(
            occurred_at=_at(1, hour=0),
            amount_minor=1200,
            direction="expense",
            merchant="早餐店",
            description="早餐",
            platform_category="餐饮/早餐",
            source_row=1,
        )
        add(
            occurred_at=_at(5),
            amount_minor=5000,
            direction="expense",
            merchant="房东",
            description="一月房租",
            platform_category="居住",
            category="住房/房租",
            source_row=2,
        )
        add(
            occurred_at=_at(10),
            amount_minor=10000,
            direction="income",
            merchant="公司",
            description="工资",
            platform_category="收入/工资",
            source_row=3,
        )
        add(
            occurred_at=_at(12),
            amount_minor=999,
            direction="expense",
            status="failed",
            merchant="失败商户",
            description="支付失败",
            source_row=4,
        )
        add(
            occurred_at=_at(15),
            amount_minor=3000,
            direction="transfer",
            merchant="银行卡",
            description="转账",
            source_row=5,
        )
        add(
            occurred_at=_at(20),
            amount_minor=500,
            direction="expense",
            status="refunded",
            merchant="退款店",
            description="退款",
            platform_category="购物",
            source_row=6,
        )
        # WeChat exports the actual refund receipt as a separate income row.
        add(
            occurred_at=_at(20, hour=12, minute=1),
            amount_minor=500,
            direction="income",
            status="refunded",
            merchant="退款店",
            description="退款回款",
            platform_category="购物",
            source_row=15,
        )
        add(
            occurred_at=_at(25),
            amount_minor=700,
            direction="expense",
            merchant="景区",
            description="门票",
            category="旅行/交通",
            source_row=7,
        )
        add(
            occurred_at=_at(28),
            amount_minor=300,
            direction="expense",
            merchant="视频会员",
            description="月度订阅",
            source_row=8,
        )
        add(
            occurred_at=_at(29),
            amount_minor=100,
            direction="expense",
            merchant="杂货店",
            description="日用品",
            source_row=9,
        )
        add(
            occurred_at=_at(31, hour=23, minute=59),
            amount_minor=400,
            direction="expense",
            merchant="月底商户",
            description="月末消费",
            source_row=14,
        )
        # Exact upper-bound day is outside the January period.
        add(
            occurred_at=_at(1, year=2026, month=2),
            amount_minor=900,
            direction="expense",
            merchant="二月商户",
            description="二月消费",
            source_row=10,
        )

        # Previous month and previous year provide comparison fixtures.
        add(
            occurred_at=_at(20, year=2025, month=12),
            amount_minor=4000,
            direction="expense",
            merchant="去年十二月商户",
            description="支出",
            source_row=11,
        )
        add(
            occurred_at=_at(22, year=2025, month=12),
            amount_minor=8000,
            direction="income",
            merchant="去年十二月公司",
            description="收入",
            source_row=12,
        )
        add(
            occurred_at=_at(10, year=2025, month=1),
            amount_minor=2500,
            direction="expense",
            merchant="去年一月商户",
            description="支出",
            source_row=13,
        )

        add(
            owner_id="owner-b",
            bill_import_id="import-b",
            occurred_at=_at(5),
            amount_minor=99999,
            direction="expense",
            merchant="其他用户商户",
            description="不应被 owner-a 看见",
            source_row=1,
        )
        db.commit()


def _period():
    return make_period(_at(1, hour=0), _at(1, hour=0, year=2026, month=2))


def test_summary_has_explicit_refund_transfer_failure_and_boundary_semantics(tmp_path):
    engine = _database(tmp_path)
    _seed(engine)
    with Session(engine) as db:
        result = get_summary(db, "owner-a", _period())

    assert result.currency == "CNY"
    assert result.expense_minor == 8200
    assert result.income_minor == 10500
    assert result.refund_minor == 500
    assert result.net_flow_minor == 2300
    assert result.expense_count == 7
    assert result.income_count == 2
    assert result.transfer_count == 1
    assert result.transaction_count == 10
    assert result.refund_count == 1
    assert result.excluded_count == 1
    assert result.fixed_expense_minor == 5300
    assert result.variable_expense_minor == 2900


def test_category_update_is_reflected_without_reimport(tmp_path):
    engine = _database(tmp_path)
    _seed(engine)
    with Session(engine) as db:
        transaction = db.scalar(
            select(Transaction).where(
                Transaction.owner_id == "owner-a",
                Transaction.source_row == 1,
            )
        )
        assert transaction is not None
        before = get_category_breakdown(db, "owner-a", _period())
        change = update_category(db, "owner-a", transaction.id, "自定义/早餐")
        assert change is not None
        after = get_category_breakdown(db, "owner-a", _period())

    assert before.items[0].category == "住房/房租"
    assert next(item for item in before.items if item.category == "餐饮/早餐").amount_minor == 1200
    assert next(item for item in after.items if item.category == "自定义/早餐").amount_minor == 1200
    assert not any(item.category == "餐饮/早餐" for item in after.items)


def test_trend_merchant_large_fixed_variable_and_budget(tmp_path):
    engine = _database(tmp_path)
    _seed(engine)
    with Session(engine) as db:
        trends = {
            granularity: get_trend(db, "owner-a", _period(), granularity)
            for granularity in ("day", "week", "month", "year")
        }
        merchants = get_top_merchants(db, "owner-a", _period(), "expense", limit=3)
        large = get_large_transactions(db, "owner-a", _period(), threshold_minor=1000, limit=10)
        fixed = get_fixed_variable(db, "owner-a", _period())
        budget = get_budget_status(db, "owner-a", _period(), 6000)

    assert len(trends["week"].items) == 5
    assert len(trends["day"].items) == 31
    assert len(trends["month"].items) == 1
    assert len(trends["year"].items) == 1
    assert sum(item.expense_minor for item in trends["week"].items) == 8200
    assert merchants.items[0].merchant == "房东"
    assert [item.amount_minor for item in large.items] == [5000, 1200]
    assert large.direction == "expense"
    assert fixed.fixed_minor == 5300
    assert fixed.variable_minor == 2900
    assert budget.used_minor == 8200
    assert budget.remaining_minor == 0
    assert budget.over_budget_minor == 2200
    assert budget.utilization_percent == pytest.approx(136.67)


def test_income_large_transactions_can_be_requested_explicitly(tmp_path):
    engine = _database(tmp_path)
    _seed(engine)
    with Session(engine) as db:
        result = get_large_transactions(
            db,
            "owner-a",
            _period(),
            threshold_minor=1500,
            limit=10,
            direction="income",
        )

    assert result.direction == "income"
    assert [item.amount_minor for item in result.items] == [10000]
    assert all(item.direction == "income" for item in result.items)


def test_comparison_supports_previous_period_and_yoy(tmp_path):
    engine = _database(tmp_path)
    _seed(engine)
    with Session(engine) as db:
        previous = compare_periods(db, "owner-a", _period(), mode="previous")
        yoy_period = make_period(_at(1, year=2026), _at(1, year=2026, month=2))
        yoy = compare_periods(db, "owner-a", yoy_period, mode="yoy")

    assert previous.comparison.expense_minor == 4000
    assert previous.metrics["expense_minor"].delta == 4200
    assert previous.comparison.income_minor == 8000
    assert yoy.comparison.expense_minor == 2500
    assert yoy.metrics["refund_minor"].current == 500


def test_owner_isolation_and_multi_currency_validation(tmp_path):
    engine = _database(tmp_path)
    _seed(engine)
    with Session(engine) as db:
        result = get_summary(db, "owner-a", _period())
        assert result.expense_minor == 8200

        transaction = db.scalar(
            select(Transaction).where(
                Transaction.owner_id == "owner-a",
                Transaction.source_row == 1,
            )
        )
        assert transaction is not None
        transaction.currency = "USD"
        db.commit()
        with pytest.raises(StatsServiceError, match="多个币种"):
            get_summary(db, "owner-a", _period())
