"""Safe command-line lifecycle operations for the local SQLite release."""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.core.config import get_settings
from app.db.session import engine
from app.services.backup_service import create_sqlite_backup, sqlite_database_path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def upgrade_database() -> int:
    """Upgrade an Alembic-managed database, always backing up stale data first."""

    settings = get_settings()
    settings.ensure_data_dirs()
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    expected_heads = set(scripts.get_heads())
    database_path = sqlite_database_path(engine)

    existing_tables = set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
    if current_heads == expected_heads:
        print("数据库已经是最新版本；未执行写入。")
        return 0
    if existing_tables and not current_heads:
        raise RuntimeError(
            "检测到未由 Alembic 管理的本地数据库；请先启动应用，让兼容升级路径创建保护备份"
        )

    if database_path.is_file() and existing_tables:
        backup = create_sqlite_backup(
            engine,
            settings.data_dir,
            settings.backup_max_bytes,
            kind="pre_upgrade",
        )
        print(f"升级前备份已创建：{backup.id}")
    command.upgrade(config, "head")
    print("数据库升级完成。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="个人消费分析本地数据管理")
    parser.add_argument("command", choices=("upgrade",))
    arguments = parser.parse_args()
    if arguments.command == "upgrade":
        return upgrade_database()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
