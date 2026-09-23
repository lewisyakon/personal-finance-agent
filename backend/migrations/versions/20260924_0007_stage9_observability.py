"""stage9 evaluation metrics and failure samples

Revision ID: 20260924_0007
Revises: 20260923_0006
"""

import sqlalchemy as sa
from alembic import op

revision = "20260924_0007"
down_revision = "20260923_0006"
branch_labels = None
depends_on = None


_METRIC_COLUMNS = (
    "task_completion_bp",
    "evidence_coverage_bp",
    "hallucination_rate_bp",
    "routing_accuracy_bp",
    "average_handoff_count_bp",
    "p50_latency_ms",
    "p95_latency_ms",
    "estimated_cost_microusd",
)


def upgrade() -> None:
    op.add_column(
        "agent_evaluation_runs",
        sa.Column("comparison_group_id", sa.String(length=36)),
    )
    op.create_index(
        "ix_agent_evaluation_runs_comparison_group_id",
        "agent_evaluation_runs",
        ["comparison_group_id"],
    )
    for name in _METRIC_COLUMNS:
        op.add_column(
            "agent_evaluation_runs",
            sa.Column(name, sa.Integer(), nullable=False, server_default="0"),
        )
    op.create_table(
        "evaluation_failure_samples",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "evaluation_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.String(length=128),
            sa.ForeignKey("workspace_owners.id"),
            nullable=False,
        ),
        sa.Column("dataset_version", sa.String(length=40), nullable=False),
        sa.Column("case_id", sa.String(length=80), nullable=False),
        sa.Column("workflow", sa.String(length=24), nullable=False),
        sa.Column("error_stage", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns in (
        ("ix_evaluation_failure_samples_evaluation_run_id", ["evaluation_run_id"]),
        ("ix_evaluation_failure_samples_owner_id", ["owner_id"]),
        ("ix_eval_failure_owner_created", ["owner_id", "created_at"]),
        ("ix_eval_failure_run_case", ["evaluation_run_id", "case_id"]),
    ):
        op.create_index(name, "evaluation_failure_samples", columns)


def downgrade() -> None:
    op.drop_table("evaluation_failure_samples")
    op.drop_index(
        "ix_agent_evaluation_runs_comparison_group_id",
        table_name="agent_evaluation_runs",
    )
    for name in reversed(_METRIC_COLUMNS):
        op.drop_column("agent_evaluation_runs", name)
    op.drop_column("agent_evaluation_runs", "comparison_group_id")
