from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.imports import owner_context
from app.db.session import get_db
from app.main import app
from app.models.base import Base
from app.models.finance import BillImport, Transaction, WorkspaceOwner

TZ = ZoneInfo("Asia/Shanghai")


def _seed_api_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'stats-api.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(WorkspaceOwner(id="api-stats-owner", display_name="API 统计测试用户"))
        db.add(
            BillImport(
                id="api-stats-import",
                owner_id="api-stats-owner",
                file_name="synthetic.csv",
                file_sha256="c" * 64,
                status="completed",
            )
        )
        rows = [
            ("2026-01-03T10:00:00", 1200, "expense", "早餐店", "餐饮/早餐", "success"),
            ("2026-01-05T10:00:00", 5000, "expense", "房东", "住房/房租", "success"),
            ("2026-01-10T10:00:00", 10000, "income", "公司", "收入/工资", "success"),
            ("2026-01-20T10:00:00", 500, "expense", "退款店", "购物", "refunded"),
            ("2026-01-20T10:01:00", 500, "income", "退款店", "购物", "refunded"),
            ("2026-01-25T10:00:00", 700, "expense", "景区", "旅行/交通", "success"),
            ("2026-01-31T23:59:59", 400, "expense", "月底商户", "其他", "success"),
            ("2026-02-01T00:00:00", 900, "expense", "二月商户", "其他", "success"),
        ]
        for index, (occurred, amount, direction, merchant, category, status) in enumerate(
            rows, start=1
        ):
            db.add(
                Transaction(
                    owner_id="api-stats-owner",
                    bill_import_id="api-stats-import",
                    fingerprint=f"api-stats-{index}",
                    platform="wechat",
                    occurred_at=datetime.fromisoformat(occurred).replace(tzinfo=TZ),
                    direction=direction,
                    amount_minor=amount,
                    currency="CNY",
                    status=status,
                    merchant=merchant,
                    description=merchant,
                    payment_method="零钱",
                    platform_category=category,
                    source_row=index,
                )
            )
        db.commit()
    return engine


def _client(engine):
    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[owner_context] = lambda: "api-stats-owner"
    return TestClient(app, backend_options={"use_uvloop": True})


def test_stats_api_exposes_all_stage3_groups(tmp_path):
    engine = _seed_api_database(tmp_path)
    client = _client(engine)
    try:
        query = "from=2026-01-01&to=2026-01-31"
        summary = client.get(f"/api/v1/stats/summary?{query}&budget_minor=6000")
        categories = client.get(f"/api/v1/stats/categories?{query}")
        trend = client.get(f"/api/v1/stats/trend?{query}&granularity=day")
        merchants = client.get(f"/api/v1/stats/merchants?{query}&limit=2")
        large = client.get(f"/api/v1/stats/large-transactions?{query}&threshold_minor=1000")
        fixed = client.get(f"/api/v1/stats/fixed-variable?{query}")
        budget = client.get(f"/api/v1/stats/budget?{query}&budget_minor=6000")
        comparison = client.get(f"/api/v1/stats/comparison?{query}&mode=previous")

        assert summary.status_code == 200
        assert summary.json()["expense_minor"] == 7800
        assert summary.json()["income_minor"] == 10500
        assert summary.json()["refund_minor"] == 500
        assert summary.json()["budget"]["over_budget_minor"] == 1800
        assert categories.status_code == 200
        assert categories.json()["items"][0]["category"] == "住房/房租"
        assert trend.status_code == 200
        assert trend.json()["granularity"] == "day"
        assert merchants.status_code == 200
        assert merchants.json()["items"][0]["merchant"] == "房东"
        assert large.status_code == 200
        assert large.json()["direction"] == "expense"
        assert [item["amount_minor"] for item in large.json()["items"]] == [5000, 1200]
        assert fixed.status_code == 200
        assert fixed.json()["fixed_minor"] == 5000
        assert budget.status_code == 200
        assert budget.json()["period"]["timezone"] == "Asia/Shanghai"
        assert budget.json()["budget"]["used_minor"] == 7800
        assert comparison.status_code == 200
        assert comparison.json()["comparison_mode"] == "previous"
    finally:
        app.dependency_overrides.clear()


def test_stats_api_validates_period_and_multi_currency(tmp_path):
    engine = _seed_api_database(tmp_path)
    client = _client(engine)
    try:
        invalid = client.get("/api/v1/stats/summary?from=2026-02-01&to=2026-01-01")
        assert invalid.status_code == 400
        assert invalid.json()["detail"]["code"] == "INVALID_PERIOD"

        with Session(engine) as db:
            db.add(
                Transaction(
                    owner_id="api-stats-owner",
                    bill_import_id="api-stats-import",
                    fingerprint="api-stats-usd",
                    platform="wechat",
                    occurred_at=datetime(2026, 1, 27, 10, tzinfo=TZ),
                    direction="expense",
                    amount_minor=100,
                    currency="USD",
                    status="success",
                    merchant="美元商户",
                    description="多币种测试",
                    payment_method="card",
                    source_row=99,
                )
            )
            db.commit()
        multi_currency = client.get("/api/v1/stats/summary?from=2026-01-01&to=2026-02-01")
        assert multi_currency.status_code == 400
        assert multi_currency.json()["detail"]["code"] == "STATS_VALIDATION_ERROR"

        invalid_direction = client.get(
            "/api/v1/stats/categories?from=2026-01-01&to=2026-02-01&direction=sideways"
        )
        assert invalid_direction.status_code == 400
        assert invalid_direction.json()["detail"]["code"] == "STATS_VALIDATION_ERROR"

        invalid_granularity = client.get(
            "/api/v1/stats/trend?from=2026-01-01&to=2026-02-01&granularity=quarter"
        )
        assert invalid_granularity.status_code == 400
        assert invalid_granularity.json()["detail"]["code"] == "STATS_VALIDATION_ERROR"

        invalid_budget = client.get(
            "/api/v1/stats/summary?from=2026-01-01&to=2026-02-01&budget_minor=-1"
        )
        assert invalid_budget.status_code == 400
        assert invalid_budget.json()["detail"]["code"] == "INVALID_BUDGET"

        invalid_threshold = client.get(
            "/api/v1/stats/large-transactions?from=2026-01-01&to=2026-02-01&threshold_minor=-1"
        )
        assert invalid_threshold.status_code == 400
        assert invalid_threshold.json()["detail"]["code"] == "INVALID_THRESHOLD"

        invalid_mode = client.get(
            "/api/v1/stats/comparison?from=2026-01-01&to=2026-02-01&mode=quarter"
        )
        assert invalid_mode.status_code == 400
        assert invalid_mode.json()["detail"]["code"] == "STATS_VALIDATION_ERROR"

        invalid_budget_type = client.get(
            "/api/v1/stats/summary?from=2026-01-01&to=2026-02-01&budget_minor=abc"
        )
        assert invalid_budget_type.status_code == 400
        assert invalid_budget_type.json()["detail"]["code"] == "INVALID_BUDGET"

        invalid_limit_type = client.get(
            "/api/v1/stats/merchants?from=2026-01-01&to=2026-02-01&limit=abc"
        )
        assert invalid_limit_type.status_code == 400
        assert invalid_limit_type.json()["detail"]["code"] == "INVALID_LIMIT"

        invalid_threshold_type = client.get(
            "/api/v1/stats/large-transactions?from=2026-01-01&to=2026-02-01&threshold_minor=abc"
        )
        assert invalid_threshold_type.status_code == 400
        assert invalid_threshold_type.json()["detail"]["code"] == "INVALID_THRESHOLD"
    finally:
        app.dependency_overrides.clear()
