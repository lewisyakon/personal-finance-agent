"""Consistent, path-confined SQLite backups for local release operations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

from sqlalchemy import Engine, MetaData, inspect

_BACKUP_ID = re.compile(r"^[0-9a-f]{32}$")
_BACKUP_LOCK = RLock()


class BackupServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class BackupRecord:
    id: str
    kind: str
    created_at: str
    size_bytes: int
    sha256: str
    schema_fingerprint: str
    database_filename: str


def sqlite_database_path(engine: Engine) -> Path:
    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        raise BackupServiceError("SQLITE_REQUIRED", "本地备份恢复仅支持文件型 SQLite")
    if engine.url.database == ":memory:":
        raise BackupServiceError("SQLITE_FILE_REQUIRED", "内存 SQLite 不支持持久备份")
    return Path(engine.url.database).resolve()


def _backups_dir(data_dir: Path) -> Path:
    directory = (data_dir / "backups").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_fingerprint(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT type, name, COALESCE(sql, '') FROM sqlite_master "
        "WHERE type IN ('table', 'index') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name"
    ).fetchall()
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_schema_fingerprint(engine: Engine) -> str:
    path = sqlite_database_path(engine)
    with sqlite3.connect(path) as connection:
        return _schema_fingerprint(connection)


def _validate_integrity(path: Path) -> str:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise BackupServiceError("BACKUP_INTEGRITY_ERROR", "SQLite 完整性校验失败")
            return _schema_fingerprint(connection)
    except sqlite3.DatabaseError as exc:
        raise BackupServiceError("BACKUP_INVALID", "备份不是有效的 SQLite 数据库") from exc


def _make_standalone(connection: sqlite3.Connection) -> None:
    """Checkpoint copied WAL state so a backup never depends on sidecar files."""

    connection.commit()
    mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()
    if mode is None or str(mode[0]).lower() != "delete":
        raise BackupServiceError("BACKUP_JOURNAL_ERROR", "无法生成独立 SQLite 备份")


def create_sqlite_backup(
    engine: Engine,
    data_dir: Path,
    max_bytes: int,
    *,
    kind: str,
) -> BackupRecord:
    with _BACKUP_LOCK:
        source_path = sqlite_database_path(engine)
        if not source_path.is_file():
            raise BackupServiceError("DATABASE_NOT_FOUND", "SQLite 数据库文件不存在")
        wal_path = Path(f"{source_path}-wal")
        source_bytes = source_path.stat().st_size + (
            wal_path.stat().st_size if wal_path.is_file() else 0
        )
        if source_bytes > max_bytes:
            raise BackupServiceError("BACKUP_TOO_LARGE", "数据库超过备份大小上限")

        directory = _backups_dir(data_dir)
        backup_id = uuid4().hex
        filename = f"{backup_id}.sqlite3"
        destination = directory / filename
        temporary = directory / f".{backup_id}.tmp"
        manifest_path = directory / f"{backup_id}.json"
        manifest_temporary = directory / f".{backup_id}.json.tmp"
        try:
            with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as source:
                with sqlite3.connect(temporary) as target:
                    source.backup(target)
                    _make_standalone(target)
            schema_fingerprint = _validate_integrity(temporary)
            size_bytes = temporary.stat().st_size
            if size_bytes > max_bytes:
                raise BackupServiceError("BACKUP_TOO_LARGE", "备份文件超过大小上限")
            record = BackupRecord(
                id=backup_id,
                kind=kind,
                created_at=datetime.now(UTC).isoformat(),
                size_bytes=size_bytes,
                sha256=_sha256_file(temporary),
                schema_fingerprint=schema_fingerprint,
                database_filename=filename,
            )
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
            manifest_temporary.write_text(
                json.dumps(asdict(record), ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            os.chmod(manifest_temporary, 0o600)
            os.replace(manifest_temporary, manifest_path)
            return record
        finally:
            temporary.unlink(missing_ok=True)
            Path(f"{temporary}-wal").unlink(missing_ok=True)
            Path(f"{temporary}-shm").unlink(missing_ok=True)
            manifest_temporary.unlink(missing_ok=True)


def _load_record(data_dir: Path, backup_id: str) -> BackupRecord | None:
    if not _BACKUP_ID.fullmatch(backup_id):
        return None
    directory = _backups_dir(data_dir)
    manifest_path = directory / f"{backup_id}.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        record = BackupRecord(**payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if record.id != backup_id or record.database_filename != f"{backup_id}.sqlite3":
        return None
    database_path = directory / record.database_filename
    if not database_path.is_file() or database_path.is_symlink():
        return None
    return record


def list_sqlite_backups(data_dir: Path) -> list[BackupRecord]:
    directory = _backups_dir(data_dir)
    records = [
        record
        for path in directory.glob("*.json")
        if (record := _load_record(data_dir, path.stem)) is not None
    ]
    return sorted(records, key=lambda item: item.created_at, reverse=True)[:200]


def get_sqlite_backup(data_dir: Path, backup_id: str) -> BackupRecord | None:
    return _load_record(data_dir, backup_id)


def restore_sqlite_backup(
    engine: Engine,
    data_dir: Path,
    max_bytes: int,
    backup_id: str,
) -> tuple[BackupRecord, BackupRecord]:
    with _BACKUP_LOCK:
        record = _load_record(data_dir, backup_id)
        if record is None:
            raise BackupServiceError("BACKUP_NOT_FOUND", "备份不存在", http_status=404)
        directory = _backups_dir(data_dir)
        source_path = directory / record.database_filename
        if source_path.stat().st_size != record.size_bytes or record.size_bytes > max_bytes:
            raise BackupServiceError("BACKUP_SIZE_MISMATCH", "备份大小校验失败")
        if _sha256_file(source_path) != record.sha256:
            raise BackupServiceError("BACKUP_DIGEST_MISMATCH", "备份哈希校验失败")
        backup_schema = _validate_integrity(source_path)
        if backup_schema != record.schema_fingerprint:
            raise BackupServiceError("BACKUP_SCHEMA_MISMATCH", "备份 Schema 指纹校验失败")
        if backup_schema != current_schema_fingerprint(engine):
            raise BackupServiceError("BACKUP_SCHEMA_INCOMPATIBLE", "备份与当前 Schema 不兼容")

        safety = create_sqlite_backup(engine, data_dir, max_bytes, kind="pre_restore")
        database_path = sqlite_database_path(engine)
        restore_temporary = database_path.with_name(f".{database_path.name}.restore.tmp")
        try:
            with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as source:
                with sqlite3.connect(restore_temporary) as target:
                    source.backup(target)
                    _make_standalone(target)
            _validate_integrity(restore_temporary)
            engine.dispose()
            Path(f"{database_path}-wal").unlink(missing_ok=True)
            Path(f"{database_path}-shm").unlink(missing_ok=True)
            os.chmod(restore_temporary, 0o600)
            os.replace(restore_temporary, database_path)
            if _validate_integrity(database_path) != backup_schema:
                raise BackupServiceError("RESTORE_VERIFY_FAILED", "恢复后校验失败")
            engine.dispose()
            return record, safety
        finally:
            restore_temporary.unlink(missing_ok=True)
            Path(f"{restore_temporary}-wal").unlink(missing_ok=True)
            Path(f"{restore_temporary}-shm").unlink(missing_ok=True)


def purge_sqlite_backups(data_dir: Path) -> int:
    directory = _backups_dir(data_dir)
    removed = 0
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix not in {".json", ".sqlite3", ".tmp"} and not (
            path.name.startswith(".")
            and path.name.endswith((".tmp-wal", ".tmp-shm", ".restore.tmp-wal", ".restore.tmp-shm"))
        ):
            continue
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def schema_upgrade_required(engine: Engine, metadata: MetaData) -> bool:
    schema = inspect(engine)
    existing_tables = set(schema.get_table_names())
    business_tables = existing_tables - {"alembic_version"}
    if not business_tables:
        return False
    expected_tables = set(metadata.tables)
    if not expected_tables.issubset(existing_tables):
        return True
    for table_name, table in metadata.tables.items():
        existing_columns = {column["name"] for column in schema.get_columns(table_name)}
        if not {column.name for column in table.columns}.issubset(existing_columns):
            return True
    return False


def protect_local_schema_upgrade(
    engine: Engine,
    metadata: MetaData,
    data_dir: Path,
    max_bytes: int,
) -> BackupRecord | None:
    if engine.url.get_backend_name() != "sqlite" or not schema_upgrade_required(engine, metadata):
        return None
    if "alembic_version" in inspect(engine).get_table_names():
        raise RuntimeError("数据库由 Alembic 管理且 Schema 不是最新，请先执行 alembic upgrade head")
    return create_sqlite_backup(engine, data_dir, max_bytes, kind="pre_upgrade")
