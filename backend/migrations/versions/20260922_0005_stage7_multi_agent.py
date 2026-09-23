"""stage7 fixed multi-agent workflow traces

Revision ID: 20260922_0005
Revises: 20260921_0004
"""

import sqlalchemy as sa
from alembic import op

revision = "20260922_0005"
down_revision = "20260921_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "workflow",
            sa.String(length=24),
            nullable=False,
            server_default="single",
        ),
    )
    op.create_index("ix_agent_runs_workflow", "agent_runs", ["workflow"])
    op.add_column(
        "agent_evaluation_runs",
        sa.Column(
            "workflow",
            sa.String(length=24),
            nullable=False,
            server_default="single",
        ),
    )
    op.create_index(
        "ix_agent_evaluation_runs_workflow",
        "agent_evaluation_runs",
        ["workflow"],
    )
    op.create_table(
        "agent_step_traces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.String(length=128),
            sa.ForeignKey("workspace_owners.id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("node", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("input_summary_json", sa.Text(), nullable=False),
        sa.Column("output_summary_json", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns in (
        ("ix_agent_step_traces_run_id", ["run_id"]),
        ("ix_agent_step_traces_owner_id", ["owner_id"]),
        ("ix_agent_step_run_sequence", ["run_id", "sequence"]),
        ("ix_agent_step_owner_created", ["owner_id", "created_at"]),
    ):
        op.create_index(name, "agent_step_traces", columns)


def downgrade() -> None:
    op.drop_table("agent_step_traces")
    op.drop_index(
        "ix_agent_evaluation_runs_workflow",
        table_name="agent_evaluation_runs",
    )
    op.drop_column("agent_evaluation_runs", "workflow")
    op.drop_index("ix_agent_runs_workflow", table_name="agent_runs")
    op.drop_column("agent_runs", "workflow")
