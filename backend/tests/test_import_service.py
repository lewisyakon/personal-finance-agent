from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.base import Base
from app.models.finance import Transaction, TransactionCategoryChange
from app.services.import_service import (
    InProcessImportExecutor,
    cleanup_expired_raw_files,
    create_import,
    get_transaction,
    list_transactions,
    update_category,
)


def _db(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    settings.ensure_data_dirs()
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    return engine


def _sample(sample_dir) -> bytes:
    return (Path(sample_dir) / "wechat_sample_utf8.csv").read_bytes()


def test_import_is_idempotent_and_transactions_are_owner_scoped(sample_dir, tmp_path, monkeypatch):
    engine = _db(tmp_path, monkeypatch)
    with Session(engine) as db:
        first, reused = create_import(db, "owner-a", "账单.csv", _sample(sample_dir))
        assert reused is False
        first = InProcessImportExecutor(db).execute(first.id, "owner-a")
        assert first.status == "completed"
        assert first.success_rows == 3
        assert db.scalar(select(func.count()).select_from(Transaction)) == 3

        same, reused = create_import(db, "owner-a", "renamed.csv", _sample(sample_dir))
        assert same.id == first.id
        assert reused is True
        assert db.scalar(select(func.count()).select_from(Transaction)) == 3

        # A different file containing the same facts is still deduplicated by
        # the owner-scoped transaction fingerprint.
        second, reused = create_import(db, "owner-a", "other.csv", _sample(sample_dir) + b"\n")
        assert reused is False
        second = InProcessImportExecutor(db).execute(second.id, "owner-a")
        assert second.success_rows == 0
        assert second.duplicate_rows == 3
        assert db.scalar(select(func.count()).select_from(Transaction)) == 3

        # The same source transaction ID is allowed for a different owner.
        third, _ = create_import(db, "owner-b", "账单.csv", _sample(sample_dir))
        third = InProcessImportExecutor(db).execute(third.id, "owner-b")
        assert third.success_rows == 3
        assert db.scalar(select(func.count()).select_from(Transaction)) == 6


def test_transaction_filters_and_user_category_audit(sample_dir, tmp_path, monkeypatch):
    engine = _db(tmp_path, monkeypatch)
    with Session(engine) as db:
        item, _ = create_import(db, "owner-a", "账单.csv", _sample(sample_dir))
        InProcessImportExecutor(db).execute(item.id, "owner-a")
        result = list_transactions(db, "owner-a", 1, 20, direction="expense", merchant="午餐")
        assert result.total == 1
        transaction = result.items[0]
        assert transaction.amount_minor == 3800
        assert transaction.occurred_at.tzinfo is not None

        change = update_category(db, "owner-a", transaction.id, "餐饮")
        assert change is not None
        assert change.previous_category is None
        assert change.new_category == "餐饮"
        assert get_transaction(db, "owner-a", transaction.id).category == "餐饮"
        assert db.scalar(select(func.count()).select_from(TransactionCategoryChange)) == 1
        assert get_transaction(db, "owner-b", transaction.id) is None


def test_failed_rows_are_retained_in_import_report(sample_dir, tmp_path, monkeypatch):
    engine = _db(tmp_path, monkeypatch)
    content = (Path(sample_dir) / "wechat_sample_with_error.csv").read_bytes()
    with Session(engine) as db:
        item, _ = create_import(db, "owner-a", "错误.csv", content)
        item = InProcessImportExecutor(db).execute(item.id, "owner-a")
        assert item.status == "partial"
        assert item.failed_rows == 1
        assert item.success_rows == 2
        assert item.error_summary and "金额" in item.error_summary


def test_raw_file_ttl_removes_source_but_keeps_transactions(sample_dir, tmp_path, monkeypatch):
    engine = _db(tmp_path, monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "raw_file_ttl_minutes", 1)
    with Session(engine) as db:
        item, _ = create_import(db, "owner-a", "账单.csv", _sample(sample_dir))
        item = InProcessImportExecutor(db).execute(item.id, "owner-a")
        raw_path = Path(item.raw_path)
        assert raw_path.is_file()
        item.created_at = item.created_at - timedelta(minutes=2)
        db.commit()
        assert cleanup_expired_raw_files(db) == 1
        db.refresh(item)
        assert item.raw_path is None
        assert db.scalar(select(func.count()).select_from(Transaction)) == 3
