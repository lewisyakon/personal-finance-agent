from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.base import Base
from app.services.import_service import InProcessImportExecutor, create_import
from app.services.stats_service import get_summary, make_period

TZ = ZoneInfo("Asia/Shanghai")
FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "datasets"
    / "sanitized_samples"
    / "stage3_stats_fixture.csv"
)


def test_stage3_hand_check_fixture_matches_documented_totals(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    settings.ensure_data_dirs()

    engine = create_engine(f"sqlite:///{tmp_path / 'stage3-fixture.db'}", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        item, reused = create_import(
            db,
            "fixture-owner",
            FIXTURE.name,
            FIXTURE.read_bytes(),
        )
        assert reused is False
        item = InProcessImportExecutor(db).execute(item.id, "fixture-owner")
        assert item.status == "completed"
        assert item.success_rows == 12
        assert item.failed_rows == 0

        period = make_period(
            datetime(2026, 1, 1, tzinfo=TZ),
            datetime(2026, 2, 1, tzinfo=TZ),
        )
        summary = get_summary(db, "fixture-owner", period, budget_minor=6000)

    assert summary.expense_minor == 8200
    assert summary.income_minor == 10500
    assert summary.refund_minor == 500
    assert summary.net_flow_minor == 2300
    assert summary.transaction_count == 10
    assert summary.transfer_count == 1
    assert summary.excluded_count == 1
    assert summary.fixed_expense_minor == 5300
    assert summary.variable_expense_minor == 2900
    assert summary.budget is not None
    assert summary.budget.used_minor == 8200
    assert summary.budget.remaining_minor == 0
    assert summary.budget.over_budget_minor == 2200
