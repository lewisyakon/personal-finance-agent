from sqlalchemy import Engine, inspect, text

from app.db.session import engine
from app.models import agent, finance, tooling  # noqa: F401  # register model metadata
from app.models.base import Base


def _upgrade_local_sqlite_compatibility(database_engine: Engine) -> None:
    """Keep create_all-managed local databases usable across MVP stages.

    Packaged deployments use Alembic. ``create_all`` cannot add the nullable
    stage 5 run link to a stage 4 table, so local SQLite gets this one safe,
    additive compatibility change on startup.
    """

    if database_engine.dialect.name != "sqlite":
        return
    schema = inspect(database_engine)
    if "tool_traces" not in schema.get_table_names():
        return
    columns = {column["name"] for column in schema.get_columns("tool_traces")}
    with database_engine.begin() as connection:
        if "run_id" not in columns:
            connection.execute(text("ALTER TABLE tool_traces ADD COLUMN run_id VARCHAR(36)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_tool_traces_run_id ON tool_traces (run_id)")
        )


def init_database() -> None:
    """Create local MVP tables when migrations have not been run yet.

    Alembic remains the upgrade path for packaged deployments; create_all keeps
    the single-process local app usable immediately after checkout.
    """

    Base.metadata.create_all(bind=engine)
    _upgrade_local_sqlite_compatibility(engine)
