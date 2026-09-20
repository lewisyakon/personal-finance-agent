"""stage4 controlled Tool trace and evidence table

Revision ID: 20260918_0002
Revises: 20260910_0001
"""

import sqlalchemy as sa
from alembic import op

revision = "20260918_0002"
down_revision = "20260910_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Align the stage 2 migration's pluralized index name with the ORM model.
    # The indexed columns do not change.
    op.drop_index("ix_transactions_owner_occurred", table_name="transactions")
    op.create_index(
        "ix_transaction_owner_occurred",
        "transactions",
        ["owner_id", "occurred_at"],
    )
    op.create_table(
        "tool_traces",
        sa.Column("evidence_id", sa.String(length=35), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(length=128),
            sa.ForeignKey("workspace_owners.id"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("arguments_json", sa.Text(), nullable=False),
        sa.Column("arguments_sha256", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("result_sha256", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
    )
    op.create_index("ix_tool_traces_owner_id", "tool_traces", ["owner_id"])
    op.create_index("ix_tool_traces_tool_name", "tool_traces", ["tool_name"])
    op.create_index("ix_tool_traces_status", "tool_traces", ["status"])
    op.create_index("ix_tool_trace_owner_started", "tool_traces", ["owner_id", "started_at"])
    op.create_index("ix_tool_trace_owner_tool", "tool_traces", ["owner_id", "tool_name"])


def downgrade() -> None:
    op.drop_table("tool_traces")
    op.drop_index("ix_transaction_owner_occurred", table_name="transactions")
    op.create_index(
        "ix_transactions_owner_occurred",
        "transactions",
        ["owner_id", "occurred_at"],
    )
