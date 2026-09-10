"""Deterministic bill import, fingerprinting and transaction management."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.finance import BillImport, Transaction, TransactionCategoryChange, WorkspaceOwner
from app.parsers.registry import parser_registry
from app.schemas.imports import (
    BillImportResponse,
    CategoryChangeResponse,
    ImportListResponse,
    TransactionListResponse,
    TransactionResponse,
)
from app.schemas.transaction import ParseReport, TransactionRecord

_SAFE_FILENAME = re.compile(r"[^\w.\-\u4e00-\u9fff]+", re.UNICODE)
_SUPPORTED_FORMATS = {"csv", "xlsx"}


class ImportExecutor(Protocol):
    def execute(self, import_id: str, owner_id: str) -> BillImport: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _safe_filename(name: str) -> str:
    name = Path(name or "账单.csv").name
    cleaned = _SAFE_FILENAME.sub("_", name).strip("._")
    return (cleaned or "账单.csv")[:255]


def _infer_format(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower().lstrip(".")
    if suffix not in _SUPPORTED_FORMATS:
        raise ValueError("当前仅支持 CSV 或 XLSX 文件")
    return suffix


def _resolve_format(file_name: str, requested_format: str | None) -> str:
    inferred = _infer_format(file_name)
    if requested_format is None or requested_format.lower() == "auto":
        return inferred
    normalized = requested_format.lower()
    if normalized not in _SUPPORTED_FORMATS:
        raise ValueError("当前仅支持 csv 或 xlsx 格式")
    if normalized != inferred:
        raise ValueError(f"format={normalized} 与文件扩展名 .{inferred} 不一致")
    return normalized


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def transaction_fingerprint(record: TransactionRecord, owner_id: str) -> str:
    """Return a stable, owner-scoped HMAC-SHA256 fingerprint."""

    if record.source_transaction_id:
        canonical = (
            f"{owner_id}|{record.platform}|source-id|"
            f"{_normalize_text(record.source_transaction_id)}"
        )
    else:
        canonical = "|".join(
            (
                owner_id,
                record.occurred_at.isoformat(),
                str(record.amount_minor),
                record.direction,
                _normalize_text(record.merchant),
                _normalize_text(record.description),
            )
        )
    secret = get_settings().fingerprint_secret.encode("utf-8")
    return hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


class InProcessImportExecutor:
    """Replaceable synchronous executor for the local MVP."""

    def __init__(self, db: Session):
        self.db = db

    def execute(self, import_id: str, owner_id: str) -> BillImport:
        bill_import = self.db.scalar(
            select(BillImport).where(BillImport.id == import_id, BillImport.owner_id == owner_id)
        )
        if bill_import is None:
            raise LookupError("导入任务不存在")
        if bill_import.status == "completed":
            return bill_import
        if not bill_import.raw_path:
            bill_import.status = "failed"
            bill_import.error_summary = "原始文件已过期，无法重试"
            bill_import.completed_at = _now()
            self.db.commit()
            return bill_import

        bill_import.status = "processing"
        bill_import.started_at = bill_import.started_at or _now()
        bill_import.updated_at = _now()
        self.db.commit()
        try:
            # Correct legacy rows created before format inference was added,
            # e.g. an .xlsx upload previously recorded as CSV.
            detected_format = _infer_format(bill_import.file_name)
            if detected_format != bill_import.format:
                bill_import.format = detected_format
                self.db.commit()
            report = parser_registry.parse(
                Path(bill_import.raw_path), bill_import.source, bill_import.format
            )
            self._persist_report(bill_import, report, owner_id)
        except Exception as exc:  # Keep user-facing error structured and short.
            # A failed insert/commit leaves SQLAlchemy's transaction in a
            # rollback-only state. Reset it before recording the terminal
            # task state so a transient failure can be retried safely.
            self.db.rollback()
            bill_import = (
                self.db.scalar(
                    select(BillImport).where(
                        BillImport.id == import_id, BillImport.owner_id == owner_id
                    )
                )
                or bill_import
            )
            bill_import.status = "failed"
            bill_import.error_summary = f"导入失败: {type(exc).__name__}"
            bill_import.completed_at = _now()
            bill_import.updated_at = _now()
            self.db.commit()
        cleanup_expired_raw_files(self.db)
        self.db.refresh(bill_import)
        return bill_import

    def _persist_report(self, bill_import: BillImport, report: ParseReport, owner_id: str) -> None:
        bill_import.total_rows = report.total_rows
        bill_import.success_rows = report.success_rows
        bill_import.failed_rows = len(report.error_rows)
        bill_import.duplicate_rows = 0
        bill_import.skipped_rows = 0
        bill_import.pending_confirmation_rows = 0
        bill_import.error_summary = (
            "; ".join(f"第{item.row_number}行: {item.message}" for item in report.error_rows[:20])
            or None
        )

        inserted = 0
        duplicates = 0
        for record in report.records:
            fingerprint = transaction_fingerprint(record, owner_id)
            values = {
                "owner_id": owner_id,
                "bill_import_id": bill_import.id,
                "fingerprint": fingerprint,
                "platform": record.platform,
                # SQLite DateTime does not retain an offset. Store UTC-naive
                # values and add the UTC offset back at the API boundary.
                "occurred_at": record.occurred_at.astimezone(UTC).replace(tzinfo=None),
                "direction": record.direction,
                "amount_minor": record.amount_minor,
                "currency": record.currency,
                "status": record.status,
                "merchant": record.merchant,
                "description": record.description,
                "payment_method": record.payment_method,
                "platform_category": record.platform_category,
                "source_transaction_id": record.source_transaction_id,
                "source_row": record.source_row,
            }
            # SQLite's conflict target is the owner+fingerprint unique key. The
            # service still exposes a database-agnostic contract to callers.
            result = self.db.execute(
                sqlite_insert(Transaction)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["owner_id", "fingerprint"])
            )
            if result.rowcount:
                inserted += 1
            else:
                duplicates += 1
        bill_import.success_rows = inserted
        bill_import.duplicate_rows = duplicates
        bill_import.status = "completed" if not report.error_rows else "partial"
        bill_import.completed_at = _now()
        bill_import.updated_at = _now()
        self.db.commit()


def ensure_owner(db: Session, owner_id: str | None = None) -> str:
    owner_id = owner_id or get_settings().local_owner_id
    owner = db.get(WorkspaceOwner, owner_id)
    if owner is None:
        db.add(WorkspaceOwner(id=owner_id, display_name="本地工作区"))
        db.commit()
    return owner_id


def cleanup_expired_raw_files(db: Session) -> int:
    """Delete source files after the configured TTL without deleting facts."""

    settings = get_settings()
    cutoff = _now() - timedelta(minutes=max(0, settings.raw_file_ttl_minutes))
    removed = 0
    changed = False
    for item in db.scalars(select(BillImport).where(BillImport.raw_path.is_not(None))):
        if item.created_at and (_aware(item.created_at) or cutoff) > cutoff:
            continue
        path = Path(item.raw_path) if item.raw_path else None
        if path and path.is_file():
            try:
                path.unlink()
                removed += 1
                changed = True
            except OSError:
                pass
        if item.raw_path is not None:
            item.raw_path = None
            changed = True
    if changed:
        db.commit()
    return removed


def create_import(
    db: Session,
    owner_id: str,
    file_name: str,
    content: bytes,
    source: str = "wechat",
    format: str | None = None,
) -> tuple[BillImport, bool]:
    settings = get_settings()
    ensure_owner(db, owner_id)
    if source != "wechat":
        raise ValueError("当前阶段仅支持 wechat 来源")
    if not content:
        raise ValueError("上传文件为空")
    if len(content) > settings.max_upload_bytes:
        raise ValueError("上传文件超过大小限制")
    safe_name = _safe_filename(file_name)
    resolved_format = _resolve_format(safe_name, format)
    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(
        select(BillImport).where(BillImport.owner_id == owner_id, BillImport.file_sha256 == digest)
    )
    if existing:
        return existing, True
    settings.ensure_data_dirs()
    path = settings.data_dir / "uploads" / f"{uuid4()}-{secrets.token_hex(4)}-{safe_name}"
    path.write_bytes(content)
    now = _now()
    item = BillImport(
        id=str(uuid4()),
        owner_id=owner_id,
        source=source,
        format=resolved_format,
        file_name=safe_name,
        file_sha256=digest,
        raw_path=str(path),
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        # Two browser requests can race on the same file hash. The unique
        # owner+hash constraint makes the winner authoritative; return it as
        # an idempotent reuse instead of surfacing a database exception.
        db.rollback()
        existing = db.scalar(
            select(BillImport).where(
                BillImport.owner_id == owner_id, BillImport.file_sha256 == digest
            )
        )
        if existing is not None:
            path.unlink(missing_ok=True)
            return existing, True
        raise
    db.refresh(item)
    return item, False


def import_response(item: BillImport, idempotent_reuse: bool = False) -> BillImportResponse:
    return BillImportResponse(
        id=item.id,
        owner_id=item.owner_id,
        source=item.source,
        format=item.format,
        file_name=item.file_name,
        file_sha256=item.file_sha256,
        status=item.status,
        error_summary=item.error_summary,
        total_rows=item.total_rows,
        success_rows=item.success_rows,
        duplicate_rows=item.duplicate_rows,
        skipped_rows=item.skipped_rows,
        failed_rows=item.failed_rows,
        pending_confirmation_rows=item.pending_confirmation_rows,
        created_at=_aware(item.created_at),
        started_at=_aware(item.started_at),
        completed_at=_aware(item.completed_at),
        raw_file_available=bool(item.raw_path and Path(item.raw_path).is_file()),
        idempotent_reuse=idempotent_reuse,
    )


def list_imports(db: Session, owner_id: str, page: int, page_size: int) -> ImportListResponse:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    query = (
        select(BillImport)
        .where(BillImport.owner_id == owner_id)
        .order_by(BillImport.created_at.desc())
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return ImportListResponse(
        items=[import_response(item) for item in items], total=total, page=page, page_size=page_size
    )


def get_import(db: Session, owner_id: str, import_id: str) -> BillImport | None:
    return db.scalar(
        select(BillImport).where(BillImport.id == import_id, BillImport.owner_id == owner_id)
    )


def _transaction_query(db: Session, owner_id: str, **filters):
    query = select(Transaction).where(Transaction.owner_id == owner_id)
    if filters.get("date_from"):
        query = query.where(Transaction.occurred_at >= filters["date_from"])
    if filters.get("date_to"):
        query = query.where(Transaction.occurred_at < filters["date_to"])
    for field in ("direction", "status", "category"):
        if filters.get(field):
            query = query.where(getattr(Transaction, field) == filters[field])
    if filters.get("merchant"):
        query = query.where(Transaction.merchant.ilike(f"%{filters['merchant']}%"))
    if filters.get("search"):
        needle = f"%{filters['search']}%"
        query = query.where(
            Transaction.merchant.ilike(needle) | Transaction.description.ilike(needle)
        )
    if filters.get("min_amount") is not None:
        query = query.where(Transaction.amount_minor >= filters["min_amount"])
    if filters.get("max_amount") is not None:
        query = query.where(Transaction.amount_minor <= filters["max_amount"])
    return query


def transaction_response(item: Transaction) -> TransactionResponse:
    return TransactionResponse(
        id=item.id,
        owner_id=item.owner_id,
        bill_import_id=item.bill_import_id,
        fingerprint=item.fingerprint,
        platform=item.platform,
        occurred_at=_aware(item.occurred_at),
        direction=item.direction,
        amount_minor=item.amount_minor,
        currency=item.currency,
        status=item.status,
        merchant=item.merchant,
        description=item.description,
        payment_method=item.payment_method,
        platform_category=item.platform_category,
        category=item.category,
        category_source=item.category_source,
        category_confidence=item.category_confidence,
        source_transaction_id=item.source_transaction_id,
        source_row=item.source_row,
        created_at=_aware(item.created_at),
        updated_at=_aware(item.updated_at),
    )


def list_transactions(
    db: Session, owner_id: str, page: int, page_size: int, **filters
) -> TransactionListResponse:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    query = _transaction_query(db, owner_id, **filters).order_by(
        Transaction.occurred_at.desc(), Transaction.id.desc()
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return TransactionListResponse(
        items=[transaction_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_transaction(db: Session, owner_id: str, transaction_id: int) -> Transaction | None:
    return db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.owner_id == owner_id
        )
    )


def update_category(
    db: Session, owner_id: str, transaction_id: int, category: str | None
) -> CategoryChangeResponse | None:
    item = get_transaction(db, owner_id, transaction_id)
    if item is None:
        return None
    previous = item.category
    item.category = category.strip() if category and category.strip() else None
    item.category_source = "user"
    item.category_confidence = 100
    item.updated_at = _now()
    change = TransactionCategoryChange(
        transaction_id=item.id,
        owner_id=owner_id,
        previous_category=previous,
        new_category=item.category,
        source="user",
    )
    db.add(change)
    db.commit()
    db.refresh(item)
    return CategoryChangeResponse(
        transaction=transaction_response(item),
        previous_category=previous,
        new_category=item.category,
        source="user",
    )


def delete_import(db: Session, owner_id: str, import_id: str) -> bool:
    item = get_import(db, owner_id, import_id)
    if item is None:
        return False
    if item.raw_path:
        path = Path(item.raw_path)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                # Facts can still be removed even if a stale source file is
                # not currently deletable; startup TTL cleanup will retry.
                pass
    db.delete(item)
    db.commit()
    return True
