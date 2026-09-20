import hashlib
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import Field
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.finance import BillImport, Transaction, TransactionCategoryChange, WorkspaceOwner
from app.models.tooling import ToolTrace
from app.services.stats_service import get_spending_summary, make_period
from app.tools.contracts import OwnerContext, ToolArguments
from app.tools.registry import ToolDefinition, ToolRegistry, readonly_tool_registry
from app.tools.runtime import EvidenceIntegrityError, ToolExecutor

TZ = ZoneInfo("Asia/Shanghai")
PERIOD_ARGUMENTS = {
    "from": "2026-01-01T00:00:00+08:00",
    "to": "2026-02-01T00:00:00+08:00",
}


def _at(day: int, *, year: int = 2026, month: int = 1) -> datetime:
    return datetime(year, month, day, 12, tzinfo=TZ)


def _seed_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'tools.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                WorkspaceOwner(id="owner-a", display_name="Tool 测试用户 A"),
                WorkspaceOwner(id="owner-b", display_name="Tool 测试用户 B"),
                BillImport(
                    id="tool-import-a",
                    owner_id="owner-a",
                    file_name="synthetic.csv",
                    file_sha256="a" * 64,
                    status="completed",
                ),
                BillImport(
                    id="tool-import-b",
                    owner_id="owner-b",
                    file_name="synthetic.csv",
                    file_sha256="b" * 64,
                    status="completed",
                ),
            ]
        )

        def add(
            source_row: int,
            occurred_at: datetime,
            amount_minor: int,
            direction: str,
            merchant: str,
            *,
            owner_id: str = "owner-a",
            import_id: str = "tool-import-a",
            status: str = "success",
            category: str | None = None,
        ) -> Transaction:
            item = Transaction(
                owner_id=owner_id,
                bill_import_id=import_id,
                fingerprint=f"{owner_id}-{source_row}",
                occurred_at=occurred_at,
                direction=direction,
                amount_minor=amount_minor,
                currency="CNY",
                status=status,
                merchant=merchant,
                description=f"{merchant}的合成测试描述",
                platform_category=category or "其他",
                category=category,
                source_row=source_row,
            )
            db.add(item)
            return item

        breakfast = add(1, _at(3), 1200, "expense", "早餐店", category="餐饮/早餐")
        add(2, _at(5), 5000, "expense", "房东", category="住房/房租")
        add(3, _at(10), 10000, "income", "公司", category="收入/工资")
        add(4, _at(20), 500, "expense", "退款店", status="refunded", category="购物")
        add(5, _at(21), 500, "income", "退款店", status="refunded", category="购物")
        add(6, _at(22), 999, "expense", "失败商户", status="failed")
        add(7, _at(20, year=2025, month=12), 4000, "expense", "上月商户")
        add(
            1,
            _at(8),
            99999,
            "expense",
            "另一用户商户",
            owner_id="owner-b",
            import_id="tool-import-b",
        )
        db.flush()
        db.add(
            TransactionCategoryChange(
                transaction_id=breakfast.id,
                owner_id="owner-a",
                previous_category="餐饮",
                new_category="餐饮/早餐",
                source="user",
            )
        )
        db.commit()
    return engine, factory


def test_all_readonly_tools_use_deterministic_services_and_bounded_results(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    context = OwnerContext(owner_id="owner-a")
    calls = {
        "get_spending_summary": {**PERIOD_ARGUMENTS, "budget_minor": 6000},
        "get_category_breakdown": {**PERIOD_ARGUMENTS, "direction": "expense"},
        "get_trend": {**PERIOD_ARGUMENTS, "granularity": "day"},
        "get_top_merchants": {**PERIOD_ARGUMENTS, "direction": "expense", "limit": 2},
        "get_large_transactions": {
            **PERIOD_ARGUMENTS,
            "direction": "expense",
            "threshold_minor": 1000,
            "limit": 2,
        },
        "search_transactions": {
            **PERIOD_ARGUMENTS,
            "direction": "expense",
            "page": 1,
            "page_size": 2,
        },
        "compare_periods": {
            **PERIOD_ARGUMENTS,
            "compare_from": "2025-12-01T00:00:00+08:00",
            "compare_to": "2026-01-01T00:00:00+08:00",
            "mode": "previous",
        },
        "get_budget_status": {**PERIOD_ARGUMENTS, "budget_minor": 6000},
        "get_merchant_history": {
            **PERIOD_ARGUMENTS,
            "merchant": "早餐店",
            "page": 1,
            "page_size": 10,
        },
    }

    with ToolExecutor(factory, timeout_seconds=2) as executor:
        results = {
            name: executor.execute(name, arguments, context) for name, arguments in calls.items()
        }

    assert set(results) == {definition.name for definition in readonly_tool_registry.definitions()}
    assert all(result.status == "success" for result in results.values())
    assert all(result.evidence_id.startswith("ev_") for result in results.values())
    assert all(result.methodology is not None for result in results.values())

    with factory() as db:
        expected = get_spending_summary(
            db,
            "owner-a",
            make_period(
                datetime(2026, 1, 1, tzinfo=TZ),
                datetime(2026, 2, 1, tzinfo=TZ),
            ),
            6000,
        )
        trace_count = db.scalar(select(func.count()).select_from(ToolTrace))

    assert results["get_spending_summary"].data == expected.model_dump(mode="json")
    assert len(results["get_top_merchants"].data["items"]) == 2
    assert len(results["search_transactions"].data["items"]) == 2
    assert results["search_transactions"].data["page_size"] == 2
    assert results["get_merchant_history"].data["user_correction_count"] == 1
    assert results["get_merchant_history"].data["user_corrections"] == [
        {"category": "餐饮/早餐", "transaction_count": 1}
    ]
    assert trace_count == len(calls)

    provider_schemas = json.dumps(readonly_tool_registry.model_tool_schemas(), ensure_ascii=False)
    assert "owner_id" not in provider_schemas


def test_owner_is_injected_and_cannot_be_switched_by_tool_arguments(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    owner_a = OwnerContext(owner_id="owner-a")
    owner_b = OwnerContext(owner_id="owner-b")

    with ToolExecutor(factory, timeout_seconds=2) as executor:
        rejected = executor.execute(
            "get_spending_summary",
            {**PERIOD_ARGUMENTS, "owner_id": "owner-b"},
            owner_a,
        )
        result_a = executor.execute("get_spending_summary", PERIOD_ARGUMENTS, owner_a)
        result_b = executor.execute("get_spending_summary", PERIOD_ARGUMENTS, owner_b)
        assert executor.replay(result_a.evidence_id, owner_b) is None

    assert rejected.status == "error"
    assert rejected.error is not None
    assert rejected.error.code == "INVALID_ARGUMENTS"
    assert result_a.data["expense_minor"] == 6700
    assert result_b.data["expense_minor"] == 99999

    with factory() as db:
        rejected_trace = db.get(ToolTrace, rejected.evidence_id)
        assert rejected_trace is not None
        assert rejected_trace.owner_id == "owner-a"
        assert "owner_id" not in rejected_trace.arguments_json


def test_invalid_arguments_return_structured_errors_and_are_traced(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    context = OwnerContext(owner_id="owner-a")
    invalid_calls = (
        (
            "get_spending_summary",
            {"from": "2026-01-01T00:00:00", "to": PERIOD_ARGUMENTS["to"]},
        ),
        (
            "search_transactions",
            {**PERIOD_ARGUMENTS, "min_amount_minor": 200, "max_amount_minor": 100},
        ),
        ("get_top_merchants", {**PERIOD_ARGUMENTS, "limit": 101}),
        ("get_budget_status", {**PERIOD_ARGUMENTS, "budget_minor": 1.5}),
        ("missing_tool", {}),
    )

    with ToolExecutor(factory, timeout_seconds=2) as executor:
        results = [executor.execute(name, arguments, context) for name, arguments in invalid_calls]

    assert [result.status for result in results] == ["error"] * 5
    assert [result.error.code for result in results if result.error] == [
        "INVALID_ARGUMENTS",
        "INVALID_ARGUMENTS",
        "INVALID_ARGUMENTS",
        "INVALID_ARGUMENTS",
        "UNKNOWN_TOOL",
    ]
    assert all(result.data is None for result in results)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ToolTrace)) == 5


def test_evidence_replay_returns_verified_immutable_snapshot(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    context = OwnerContext(owner_id="owner-a")

    with ToolExecutor(factory, timeout_seconds=2) as executor:
        original = executor.execute("get_spending_summary", PERIOD_ARGUMENTS, context)
        with factory() as db:
            item = db.scalar(
                select(Transaction).where(
                    Transaction.owner_id == "owner-a",
                    Transaction.merchant == "早餐店",
                )
            )
            assert item is not None
            item.amount_minor = 9999
            db.commit()
        current = executor.execute("get_spending_summary", PERIOD_ARGUMENTS, context)
        replayed = executor.replay(original.evidence_id, context)

        with factory() as db:
            trace = db.get(ToolTrace, original.evidence_id)
            assert trace is not None
            trace.result_json = f"{trace.result_json} "
            db.commit()
        with pytest.raises(EvidenceIntegrityError):
            executor.replay(original.evidence_id, context)

    assert replayed is not None
    assert replayed.replayed is True
    assert replayed.evidence_id == original.evidence_id
    assert replayed.data == original.data
    assert replayed.data != current.data

    with factory() as db:
        trace = db.get(ToolTrace, current.evidence_id)
        assert trace is not None
        assert hashlib.sha256(trace.result_json.encode()).hexdigest() == trace.result_sha256
        assert hashlib.sha256(trace.arguments_json.encode()).hexdigest() == trace.arguments_sha256


class SlowArguments(ToolArguments):
    delay_seconds: float = Field(ge=0, le=1)


def _slow_handler(_db, _context, arguments):
    time.sleep(arguments.delay_seconds)
    return {"completed": True}


def test_tool_timeout_returns_structured_error_and_trace(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="slow_read",
            description="用于验证受控超时的只读测试 Tool。",
            arguments_model=SlowArguments,
            handler=_slow_handler,
            source_service="transaction_service",
        )
    )

    with ToolExecutor(factory, registry=registry, timeout_seconds=0.005, max_workers=1) as executor:
        result = executor.execute(
            "slow_read",
            {"delay_seconds": 0.05},
            OwnerContext(owner_id="owner-a"),
        )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "TOOL_TIMEOUT"
    with factory() as db:
        trace = db.get(ToolTrace, result.evidence_id)
        assert trace is not None
        assert trace.error_code == "TOOL_TIMEOUT"


class EmptyArguments(ToolArguments):
    pass


def _large_result_handler(_db, _context, _arguments):
    return {"payload": "x" * 2000}


def test_tool_result_size_is_bounded(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="large_read",
            description="用于验证结果大小限制的只读测试 Tool。",
            arguments_model=EmptyArguments,
            handler=_large_result_handler,
            source_service="transaction_service",
        )
    )

    with ToolExecutor(
        factory,
        registry=registry,
        timeout_seconds=1,
        max_result_bytes=1024,
    ) as executor:
        result = executor.execute(
            "large_read",
            {},
            OwnerContext(owner_id="owner-a"),
        )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "TOOL_RESULT_TOO_LARGE"
    with factory() as db:
        trace = db.get(ToolTrace, result.evidence_id)
        assert trace is not None
        assert trace.error_code == "TOOL_RESULT_TOO_LARGE"
        assert "payload" not in trace.result_json
