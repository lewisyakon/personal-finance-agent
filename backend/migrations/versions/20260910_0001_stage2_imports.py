"""stage2 import and transaction management tables

Revision ID: 20260910_0001
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "20260910_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_owners",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "bill_imports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(length=128), sa.ForeignKey("workspace_owners.id"), nullable=False
        ),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_path", sa.String(length=1000)),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_summary", sa.Text),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("success_rows", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False),
        sa.Column("skipped_rows", sa.Integer(), nullable=False),
        sa.Column("failed_rows", sa.Integer(), nullable=False),
        sa.Column("pending_confirmation_rows", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "file_sha256", name="uq_bill_import_owner_file"),
    )
    op.create_index("ix_bill_import_owner_created", "bill_imports", ["owner_id", "created_at"])
    op.create_index("ix_bill_imports_owner_id", "bill_imports", ["owner_id"])
    op.create_index("ix_bill_imports_file_sha256", "bill_imports", ["file_sha256"])
    op.create_index("ix_bill_imports_status", "bill_imports", ["status"])
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id", sa.String(length=128), sa.ForeignKey("workspace_owners.id"), nullable=False
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("parent_name", sa.String(length=100)),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("owner_id", "name", name="uq_category_owner_name"),
    )
    op.create_index("ix_categories_owner_id", "categories", ["owner_id"])
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id", sa.String(length=128), sa.ForeignKey("workspace_owners.id"), nullable=False
        ),
        sa.Column(
            "bill_import_id",
            sa.String(length=36),
            sa.ForeignKey("bill_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("payment_method", sa.String(length=120), nullable=False),
        sa.Column("platform_category", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=100)),
        sa.Column("category_source", sa.String(length=30)),
        sa.Column("category_confidence", sa.Integer()),
        sa.Column("source_transaction_id", sa.String(length=255)),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "fingerprint", name="uq_transaction_owner_fingerprint"),
    )
    for name, columns in (
        ("ix_transactions_owner_id", ["owner_id"]),
        ("ix_transactions_bill_import_id", ["bill_import_id"]),
        ("ix_transactions_occurred_at", ["occurred_at"]),
        ("ix_transactions_direction", ["direction"]),
        ("ix_transactions_status", ["status"]),
        ("ix_transactions_category", ["category"]),
        ("ix_transactions_owner_occurred", ["owner_id", "occurred_at"]),
        ("ix_transaction_owner_category", ["owner_id", "category"]),
        ("ix_transaction_owner_merchant", ["owner_id", "merchant"]),
    ):
        op.create_index(name, "transactions", columns)
    op.create_table(
        "transaction_category_changes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id", sa.String(length=128), sa.ForeignKey("workspace_owners.id"), nullable=False
        ),
        sa.Column("previous_category", sa.String(length=100)),
        sa.Column("new_category", sa.String(length=100)),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_transaction_category_changes_transaction_id",
        "transaction_category_changes",
        ["transaction_id"],
    )
    op.create_index(
        "ix_transaction_category_changes_owner_id", "transaction_category_changes", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_table("transaction_category_changes")
    op.drop_table("transactions")
    op.drop_table("categories")
    op.drop_table("bill_imports")
    op.drop_table("workspace_owners")
