from sqlalchemy import create_engine, inspect, text

from app.db.init import _upgrade_local_sqlite_compatibility


def test_local_create_all_database_gets_stage5_tool_run_link(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stage4.db'}", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE tool_traces ("
                "evidence_id VARCHAR(35) PRIMARY KEY, "
                "owner_id VARCHAR(128) NOT NULL"
                ")"
            )
        )

    _upgrade_local_sqlite_compatibility(engine)
    _upgrade_local_sqlite_compatibility(engine)

    schema = inspect(engine)
    assert "run_id" in {column["name"] for column in schema.get_columns("tool_traces")}
    assert "ix_tool_traces_run_id" in {index["name"] for index in schema.get_indexes("tool_traces")}
