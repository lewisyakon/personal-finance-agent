"""stage10 versioned memories and retrieval traces

Revision ID: 20260925_0008
Revises: 20260924_0007
"""

import sqlalchemy as sa
from alembic import op

revision = "20260925_0008"
down_revision = "20260924_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=128), sa.ForeignKey("workspace_owners.id"), nullable=False),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("memory_key", sa.String(length=200), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_ref_type", sa.String(length=40)),
        sa.Column("source_ref_id", sa.String(length=64)),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_id", sa.String(length=36), sa.ForeignKey("memory_records.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns in (
        ("ix_memory_records_owner_id", ["owner_id"]),
        ("ix_memory_records_scope", ["scope"]),
        ("ix_memory_records_kind", ["kind"]),
        ("ix_memory_records_status", ["status"]),
        ("ix_memory_owner_scope_status", ["owner_id", "scope", "status"]),
        ("ix_memory_owner_kind_key", ["owner_id", "kind", "memory_key"]),
    ):
        op.create_index(name, "memory_records", columns)

    op.create_table(
        "memory_access_traces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=128), sa.ForeignKey("workspace_owners.id"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE")),
        sa.Column("query_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("matched_memory_ids_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns in (
        ("ix_memory_access_traces_owner_id", ["owner_id"]),
        ("ix_memory_access_traces_run_id", ["run_id"]),
        ("ix_memory_access_traces_status", ["status"]),
        ("ix_memory_access_owner_created", ["owner_id", "created_at"]),
        ("ix_memory_access_run_created", ["run_id", "created_at"]),
    ):
        op.create_index(name, "memory_access_traces", columns)


def downgrade() -> None:
    op.drop_table("memory_access_traces")
    op.drop_table("memory_records")
