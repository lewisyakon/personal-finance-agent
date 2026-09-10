"""Persistence models for the import and transaction management stage.

The MVP deliberately keeps the model set small, but every row is owner scoped
so the same service can later be used by an authenticated hosted deployment.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.models.base import Base


class AwareDateTime(TypeDecorator):
    """Persist timezone-aware UTC values even on SQLite.

    SQLite's native datetime adapter drops offsets. The decorator stores a UTC
    naive value in the file (portable across SQLite versions) and restores the
    explicit UTC offset whenever a row is read by SQLAlchemy.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorkspaceOwner(Base):
    __tablename__ = "workspace_owners"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), default="本地工作区")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)

    imports: Mapped[list["BillImport"]] = relationship(back_populates="owner")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="owner")


class BillImport(Base):
    __tablename__ = "bill_imports"
    __table_args__ = (
        UniqueConstraint("owner_id", "file_sha256", name="uq_bill_import_owner_file"),
        Index("ix_bill_import_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="wechat")
    format: Mapped[str] = mapped_column(String(20), default="csv")
    file_name: Mapped[str] = mapped_column(String(255), default="账单.csv")
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    raw_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    success_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    pending_confirmation_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now, onupdate=utc_now)

    owner: Mapped[WorkspaceOwner] = relationship(back_populates="imports")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="bill_import", cascade="all, delete-orphan"
    )


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_category_owner_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_system: Mapped[bool] = mapped_column(default=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("owner_id", "fingerprint", name="uq_transaction_owner_fingerprint"),
        Index("ix_transaction_owner_occurred", "owner_id", "occurred_at"),
        Index("ix_transaction_owner_category", "owner_id", "category"),
        Index("ix_transaction_owner_merchant", "owner_id", "merchant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    bill_import_id: Mapped[str] = mapped_column(
        ForeignKey("bill_imports.id", ondelete="CASCADE"), index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(40), default="wechat")
    occurred_at: Mapped[datetime] = mapped_column(AwareDateTime(), index=True)
    direction: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    status: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    merchant: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    payment_method: Mapped[str] = mapped_column(String(120), default="")
    platform_category: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    category_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    category_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_row: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now, onupdate=utc_now)

    owner: Mapped[WorkspaceOwner] = relationship(back_populates="transactions")
    bill_import: Mapped[BillImport] = relationship(back_populates="transactions")
    category_changes: Mapped[list["TransactionCategoryChange"]] = relationship(
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionCategoryChange.created_at",
    )


class TransactionCategoryChange(Base):
    __tablename__ = "transaction_category_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    previous_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="user")
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)

    transaction: Mapped[Transaction] = relationship(back_populates="category_changes")
