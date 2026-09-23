from sqlalchemy import Engine, inspect, text

from app.core.config import Settings, get_settings
from app.db.session import engine
from app.models import (  # noqa: F401  # register model metadata
    agent,
    finance,
    memory,
    multi_agent,
    planning,
    semantic,
    tooling,
)
from app.models.base import Base
from app.services.backup_service import BackupRecord, protect_local_schema_upgrade


def _upgrade_local_sqlite_compatibility(database_engine: Engine) -> None:
    """Keep create_all-managed local databases usable across MVP stages.

    Packaged deployments use Alembic. ``create_all`` cannot add the nullable
    stage 5 run link to a stage 4 table, so local SQLite gets this one safe,
    additive compatibility change on startup.
    """

    if database_engine.dialect.name != "sqlite":
        return
    schema = inspect(database_engine)
    table_names = schema.get_table_names()
    if "tool_traces" in table_names:
        columns = {column["name"] for column in schema.get_columns("tool_traces")}
        with database_engine.begin() as connection:
            if "run_id" not in columns:
                connection.execute(text("ALTER TABLE tool_traces ADD COLUMN run_id VARCHAR(36)"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_tool_traces_run_id ON tool_traces (run_id)")
            )
    schema = inspect(database_engine)
    table_names = schema.get_table_names()
    if "agent_runs" in table_names:
        run_columns = {column["name"] for column in schema.get_columns("agent_runs")}
        with database_engine.begin() as connection:
            if "workflow" not in run_columns:
                connection.execute(
                    text(
                        "ALTER TABLE agent_runs ADD COLUMN workflow VARCHAR(24) "
                        "NOT NULL DEFAULT 'single'"
                    )
                )
            if "estimated_cost_microusd" not in run_columns:
                connection.execute(
                    text(
                        "ALTER TABLE agent_runs ADD COLUMN estimated_cost_microusd "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_agent_runs_workflow ON agent_runs (workflow)")
            )
    if "agent_evaluation_runs" in table_names:
        eval_columns = {column["name"] for column in schema.get_columns("agent_evaluation_runs")}
        with database_engine.begin() as connection:
            if "workflow" not in eval_columns:
                connection.execute(
                    text(
                        "ALTER TABLE agent_evaluation_runs ADD COLUMN workflow VARCHAR(24) "
                        "NOT NULL DEFAULT 'single'"
                    )
                )
            additive_eval_columns = {
                "comparison_group_id": "VARCHAR(36)",
                "task_completion_bp": "INTEGER NOT NULL DEFAULT 0",
                "evidence_coverage_bp": "INTEGER NOT NULL DEFAULT 0",
                "hallucination_rate_bp": "INTEGER NOT NULL DEFAULT 0",
                "routing_accuracy_bp": "INTEGER NOT NULL DEFAULT 0",
                "average_handoff_count_bp": "INTEGER NOT NULL DEFAULT 0",
                "p50_latency_ms": "INTEGER NOT NULL DEFAULT 0",
                "p95_latency_ms": "INTEGER NOT NULL DEFAULT 0",
                "estimated_cost_microusd": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, sql_type in additive_eval_columns.items():
                if name not in eval_columns:
                    connection.execute(
                        text(f"ALTER TABLE agent_evaluation_runs ADD COLUMN {name} {sql_type}")
                    )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_agent_evaluation_runs_workflow "
                    "ON agent_evaluation_runs (workflow)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_agent_evaluation_runs_comparison_group_id "
                    "ON agent_evaluation_runs (comparison_group_id)"
                )
            )


def init_database(
    database_engine: Engine = engine,
    settings: Settings | None = None,
) -> BackupRecord | None:
    """Create local MVP tables when migrations have not been run yet.

    Alembic remains the upgrade path for packaged deployments; create_all keeps
    the single-process local app usable immediately after checkout.
    """

    selected_settings = settings or get_settings()
    protected_backup = protect_local_schema_upgrade(
        database_engine,
        Base.metadata,
        selected_settings.data_dir,
        selected_settings.backup_max_bytes,
    )
    Base.metadata.create_all(bind=database_engine)
    _upgrade_local_sqlite_compatibility(database_engine)
    return protected_backup
