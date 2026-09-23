"""stage5 model and single-agent run tables

Revision ID: 20260920_0003
Revises: 20260918_0002
"""

import sqlalchemy as sa
from alembic import op

revision = "20260920_0003"
down_revision = "20260918_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(length=128),
            sa.ForeignKey("workspace_owners.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_sessions_owner_id", "agent_sessions", ["owner_id"])
    op.create_index("ix_agent_session_owner_updated", "agent_sessions", ["owner_id", "updated_at"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.String(length=128),
            sa.ForeignKey("workspace_owners.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_message", sa.String(length=500)),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("tool_call_count", sa.Integer(), nullable=False),
        sa.Column("model_call_count", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False),
        sa.Column("tool_names_json", sa.Text(), nullable=False),
        sa.Column("cancellation_requested", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
    )
    for name, columns in (
        ("ix_agent_runs_session_id", ["session_id"]),
        ("ix_agent_runs_owner_id", ["owner_id"]),
        ("ix_agent_runs_status", ["status"]),
        ("ix_agent_run_owner_started", ["owner_id", "started_at"]),
        ("ix_agent_run_session_started", ["session_id", "started_at"]),
    ):
        op.create_index(name, "agent_runs", columns)

    op.create_table(
        "model_call_traces",
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
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("selected_tools_json", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns in (
        ("ix_model_call_traces_run_id", ["run_id"]),
        ("ix_model_call_traces_owner_id", ["owner_id"]),
        ("ix_model_call_run_sequence", ["run_id", "sequence"]),
    ):
        op.create_index(name, "model_call_traces", columns)

    op.create_table(
        "agent_evaluation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(length=128),
            sa.ForeignKey("workspace_owners.id"),
            nullable=False,
        ),
        sa.Column("dataset_version", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("tool_selection_accuracy_bp", sa.Integer(), nullable=False),
        sa.Column("numeric_accuracy_bp", sa.Integer(), nullable=False),
        sa.Column("average_latency_ms", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("results_json", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    for name, columns in (
        ("ix_agent_evaluation_runs_owner_id", ["owner_id"]),
        ("ix_agent_evaluation_runs_status", ["status"]),
        ("ix_agent_eval_owner_started", ["owner_id", "started_at"]),
    ):
        op.create_index(name, "agent_evaluation_runs", columns)

    op.add_column("tool_traces", sa.Column("run_id", sa.String(length=36), nullable=True))
    op.create_index("ix_tool_traces_run_id", "tool_traces", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_traces_run_id", table_name="tool_traces")
    op.drop_column("tool_traces", "run_id")
    op.drop_table("agent_evaluation_runs")
    op.drop_table("model_call_traces")
    op.drop_table("agent_runs")
    op.drop_table("agent_sessions")
