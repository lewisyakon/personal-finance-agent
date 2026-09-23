"""stage6 semantic classification and merchant rules

Revision ID: 20260921_0004
Revises: 20260920_0003
"""

import sqlalchemy as sa
from alembic import op

revision = "20260921_0004"
down_revision = "20260920_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "merchant_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(length=128),
            sa.ForeignKey("workspace_owners.id"),
            nullable=False,
        ),
        sa.Column("normalized_merchant", sa.String(length=255), nullable=False),
        sa.Column("display_merchant", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_id",
            "normalized_merchant",
            name="uq_merchant_rule_owner_normalized",
        ),
    )
    op.create_index("ix_merchant_rules_owner_id", "merchant_rules", ["owner_id"])
    op.create_index("ix_merchant_rule_owner_active", "merchant_rules", ["owner_id", "active"])

    op.create_table(
        "classification_suggestions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.String(length=128),
            sa.ForeignKey("workspace_owners.id"),
            nullable=False,
        ),
        sa.Column("normalized_merchant", sa.String(length=255), nullable=False),
        sa.Column("suggested_category", sa.String(length=100), nullable=False),
        sa.Column("confidence_bp", sa.Integer(), nullable=False),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False),
        sa.Column("rationale_summary", sa.String(length=500), nullable=False),
        sa.Column("route", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=40)),
        sa.Column("model", sa.String(length=200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    for name, columns in (
        ("ix_classification_suggestions_transaction_id", ["transaction_id"]),
        ("ix_classification_suggestions_owner_id", ["owner_id"]),
        ("ix_classification_suggestions_normalized_merchant", ["normalized_merchant"]),
        ("ix_classification_suggestions_status", ["status"]),
        ("ix_classification_owner_status", ["owner_id", "status"]),
        ("ix_classification_transaction_created", ["transaction_id", "created_at"]),
    ):
        op.create_index(name, "classification_suggestions", columns)


def downgrade() -> None:
    op.drop_table("classification_suggestions")
    op.drop_table("merchant_rules")
