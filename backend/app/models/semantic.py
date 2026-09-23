"""Persistent user merchant rules and semantic classification suggestions."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.finance import AwareDateTime, utc_now


class MerchantRule(Base):
    __tablename__ = "merchant_rules"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "normalized_merchant",
            name="uq_merchant_rule_owner_normalized",
        ),
        Index("ix_merchant_rule_owner_active", "owner_id", "active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    normalized_merchant: Mapped[str] = mapped_column(String(255))
    display_merchant: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(30), default="user_confirmed")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now, onupdate=utc_now)


class ClassificationSuggestion(Base):
    __tablename__ = "classification_suggestions"
    __table_args__ = (
        Index("ix_classification_owner_status", "owner_id", "status"),
        Index("ix_classification_transaction_created", "transaction_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("workspace_owners.id"), index=True)
    normalized_merchant: Mapped[str] = mapped_column(String(255), index=True)
    suggested_category: Mapped[str] = mapped_column(String(100))
    confidence_bp: Mapped[int] = mapped_column(Integer)
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    rationale_summary: Mapped[str] = mapped_column(String(500), default="")
    route: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(24), index=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime(), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(AwareDateTime(), nullable=True)
