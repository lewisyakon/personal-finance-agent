"""stage8 planner budgets and confirmations

Revision ID: 20260923_0006
Revises: 20260922_0005
"""

import sqlalchemy as sa
from alembic import op

revision = "20260923_0006"
down_revision = "20260922_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "estimated_cost_microusd",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_table(
        "agent_plan_traces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id", sa.String(length=128), sa.ForeignKey("workspace_owners.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("validation_errors_json", sa.Text(), nullable=False),
        sa.Column("replan_reason", sa.String(length=200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns in (
        ("ix_agent_plan_traces_run_id", ["run_id"]),
        ("ix_agent_plan_traces_owner_id", ["owner_id"]),
        ("ix_agent_plan_run_version", ["run_id", "version"]),
        ("ix_agent_plan_owner_created", ["owner_id", "created_at"]),
    ):
        op.create_index(name, "agent_plan_traces", columns)

    op.create_table(
        "budget_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(length=128), sa.ForeignKey("workspace_owners.id"), nullable=False
        ),
        sa.Column(
            "run_id", sa.String(length=36), sa.ForeignKey("agent_runs.id", ondelete="SET NULL")
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("baseline_expense_minor", sa.Integer(), nullable=False),
        sa.Column("proposed_budget_minor", sa.Integer(), nullable=False),
        sa.Column("reduction_bp", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )
    for name, columns in (
        ("ix_budget_plans_owner_id", ["owner_id"]),
        ("ix_budget_plans_run_id", ["run_id"]),
        ("ix_budget_plans_status", ["status"]),
        ("ix_budget_plan_owner_status", ["owner_id", "status"]),
        ("ix_budget_plan_owner_period", ["owner_id", "period_start", "period_end"]),
    ):
        op.create_index(name, "budget_plans", columns)

    op.create_table(
        "agent_confirmations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(length=128), sa.ForeignKey("workspace_owners.id"), nullable=False
        ),
        sa.Column(
            "run_id", sa.String(length=36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE")
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("target_id", sa.String(length=36)),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("prompt_summary", sa.String(length=500), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    for name, columns in (
        ("ix_agent_confirmations_owner_id", ["owner_id"]),
        ("ix_agent_confirmations_run_id", ["run_id"]),
        ("ix_agent_confirmations_status", ["status"]),
        ("ix_agent_confirmation_owner_status", ["owner_id", "status"]),
        ("ix_agent_confirmation_run", ["run_id", "created_at"]),
    ):
        op.create_index(name, "agent_confirmations", columns)


def downgrade() -> None:
    op.drop_table("agent_confirmations")
    op.drop_table("budget_plans")
    op.drop_table("agent_plan_traces")
    op.drop_column("agent_runs", "estimated_cost_microusd")
