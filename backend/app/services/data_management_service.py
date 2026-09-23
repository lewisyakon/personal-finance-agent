"""Confirmed local data lifecycle operations with bounded, owner-scoped exports."""

from __future__ import annotations

import hashlib
import json
import secrets
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Any

from sqlalchemy import Engine, delete, select, text

from app import models as _models  # noqa: F401  # register complete metadata
from app.core.config import Settings, get_settings
from app.models.base import Base
from app.models.finance import BillImport, WorkspaceOwner
from app.schemas.data_management import (
    BackupListResponse,
    BackupResponse,
    DataConfirmationRequest,
    DataConfirmationResponse,
    DeleteAllResponse,
    LocalDataStatusResponse,
    RestoreResponse,
)
from app.services.backup_service import (
    BackupRecord,
    BackupServiceError,
    create_sqlite_backup,
    get_sqlite_backup,
    list_sqlite_backups,
    purge_sqlite_backups,
    restore_sqlite_backup,
    sqlite_database_path,
)
from app.services.import_service import ensure_owner

_CONFIRMATION_PHRASES = {
    "export": "导出我的数据",
    "delete_all": "删除全部数据",
    "backup": "创建本地备份",
    "restore": "恢复本地备份",
}


class DataManagementError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class ExportArchive:
    filename: str
    content: bytes


@dataclass(frozen=True)
class _Confirmation:
    owner_id: str
    action: str
    target_id: str | None
    expires_clock: float
    expires_at: datetime


class DataConfirmationStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, _Confirmation] = {}
        self._lock = RLock()

    def issue(
        self,
        owner_id: str,
        action: str,
        target_id: str | None,
        confirmation_text: str,
    ) -> DataConfirmationResponse:
        expected = _CONFIRMATION_PHRASES[action]
        if not secrets.compare_digest(
            confirmation_text.strip().encode("utf-8"), expected.encode("utf-8")
        ):
            raise DataManagementError("CONFIRMATION_TEXT_MISMATCH", "确认文字不匹配")
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        with self._lock:
            self._purge_expired()
            self._items[digest] = _Confirmation(
                owner_id=owner_id,
                action=action,
                target_id=target_id,
                expires_clock=monotonic() + self.ttl_seconds,
                expires_at=expires_at,
            )
        return DataConfirmationResponse(
            action=action,
            target_id=target_id,
            confirmation_token=token,
            expires_at=expires_at,
        )

    def consume(
        self,
        token: str,
        owner_id: str,
        action: str,
        target_id: str | None = None,
    ) -> None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            self._purge_expired()
            item = self._items.get(digest)
            if item is None:
                raise DataManagementError("CONFIRMATION_INVALID", "确认令牌无效或已使用")
            if (
                item.owner_id != owner_id
                or item.action != action
                or item.target_id != target_id
            ):
                raise DataManagementError("CONFIRMATION_SCOPE_MISMATCH", "确认令牌范围不匹配")
            self._items.pop(digest, None)

    def _purge_expired(self) -> None:
        now = monotonic()
        for digest, item in list(self._items.items()):
            if item.expires_clock <= now:
                self._items.pop(digest, None)


def _backup_response(item: BackupRecord) -> BackupResponse:
    return BackupResponse(
        id=item.id,
        kind=item.kind,
        created_at=datetime.fromisoformat(item.created_at),
        size_bytes=item.size_bytes,
        sha256=item.sha256,
        schema_fingerprint=item.schema_fingerprint,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


class DataManagementService:
    def __init__(
        self,
        session_factory,
        engine: Engine,
        *,
        settings: Settings | None = None,
        confirmations: DataConfirmationStore | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.engine = engine
        self.settings = settings or get_settings()
        self.confirmations = confirmations or DataConfirmationStore(
            self.settings.data_confirmation_ttl_seconds
        )
        self._operation_lock = RLock()

    def issue_confirmation(
        self, owner_id: str, payload: DataConfirmationRequest
    ) -> DataConfirmationResponse:
        if payload.action == "restore" and get_sqlite_backup(
            self.settings.data_dir, payload.target_id or ""
        ) is None:
            raise DataManagementError("BACKUP_NOT_FOUND", "备份不存在", http_status=404)
        return self.confirmations.issue(
            owner_id,
            payload.action,
            payload.target_id,
            payload.confirmation_text,
        )

    def status(self) -> LocalDataStatusResponse:
        database_path = sqlite_database_path(self.engine)
        uploads_dir = (self.settings.data_dir / "uploads").resolve()
        raw_file_count = (
            sum(1 for path in uploads_dir.iterdir() if path.is_file() and not path.is_symlink())
            if uploads_dir.is_dir()
            else 0
        )
        return LocalDataStatusResponse(
            data_directory=str(self.settings.data_dir.resolve()),
            database_size_bytes=database_path.stat().st_size if database_path.is_file() else 0,
            raw_file_count=raw_file_count,
            backup_count=len(list_sqlite_backups(self.settings.data_dir)),
            raw_file_ttl_minutes=max(0, self.settings.raw_file_ttl_minutes),
        )

    def export_data(self, owner_id: str, confirmation_token: str) -> ExportArchive:
        self.confirmations.consume(confirmation_token, owner_id, "export")
        with self._operation_lock:
            table_payloads: dict[str, bytes] = {}
            counts: dict[str, int] = {}
            total_bytes = 0
            with self.session_factory() as db:
                ensure_owner(db, owner_id)
                for table in Base.metadata.sorted_tables:
                    if "owner_id" in table.c:
                        rows = db.execute(
                            select(table).where(table.c.owner_id == owner_id)
                        ).mappings()
                    elif table.name == WorkspaceOwner.__tablename__:
                        rows = db.execute(select(table).where(table.c.id == owner_id)).mappings()
                    else:
                        continue
                    serialized = [
                        {
                            key: _json_value(value)
                            for key, value in row.items()
                            if not (table.name == "bill_imports" and key == "raw_path")
                        }
                        for row in rows
                    ]
                    content = json.dumps(
                        serialized,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    total_bytes += len(content)
                    if total_bytes > self.settings.data_export_max_bytes:
                        raise DataManagementError("EXPORT_TOO_LARGE", "数据导出超过大小上限")
                    table_payloads[f"data/{table.name}.json"] = content
                    counts[table.name] = len(serialized)
            manifest = json.dumps(
                {
                    "format": "personal-finance-export-v1",
                    "created_at": datetime.now(UTC).isoformat(),
                    "owner_id": owner_id,
                    "table_counts": counts,
                    "raw_files_included": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            archive_buffer = BytesIO()
            with zipfile.ZipFile(
                archive_buffer,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                archive.writestr("manifest.json", manifest)
                for name, content in table_payloads.items():
                    archive.writestr(name, content)
            content = archive_buffer.getvalue()
            if len(content) > self.settings.data_export_max_bytes:
                raise DataManagementError("EXPORT_TOO_LARGE", "数据导出超过大小上限")
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            return ExportArchive(
                filename=f"personal-finance-export-{timestamp}.zip",
                content=content,
            )

    def list_backups(self) -> BackupListResponse:
        items = [_backup_response(item) for item in list_sqlite_backups(self.settings.data_dir)]
        return BackupListResponse(items=items, total=len(items))

    def create_backup(self, owner_id: str, confirmation_token: str) -> BackupResponse:
        self.confirmations.consume(confirmation_token, owner_id, "backup")
        with self._operation_lock:
            return _backup_response(
                create_sqlite_backup(
                    self.engine,
                    self.settings.data_dir,
                    self.settings.backup_max_bytes,
                    kind="manual",
                )
            )

    def restore_backup(
        self, owner_id: str, backup_id: str, confirmation_token: str
    ) -> RestoreResponse:
        self.confirmations.consume(confirmation_token, owner_id, "restore", backup_id)
        with self._operation_lock:
            try:
                restored, safety = restore_sqlite_backup(
                    self.engine,
                    self.settings.data_dir,
                    self.settings.backup_max_bytes,
                    backup_id,
                )
            except BackupServiceError as exc:
                raise DataManagementError(
                    exc.code, exc.message, http_status=exc.http_status
                ) from exc
            return RestoreResponse(
                restored_backup=_backup_response(restored),
                safety_backup=_backup_response(safety),
            )

    def delete_all(self, owner_id: str, confirmation_token: str) -> DeleteAllResponse:
        self.confirmations.consume(confirmation_token, owner_id, "delete_all")
        with self._operation_lock:
            with self.session_factory() as db:
                raw_paths = list(
                    db.scalars(
                        select(BillImport.raw_path).where(
                            BillImport.owner_id == owner_id,
                            BillImport.raw_path.is_not(None),
                        )
                    )
                )
                db.execute(text("PRAGMA secure_delete=ON"))
                deleted_rows = 0
                for table in reversed(Base.metadata.sorted_tables):
                    if "owner_id" in table.c:
                        result = db.execute(delete(table).where(table.c.owner_id == owner_id))
                    elif table.name == WorkspaceOwner.__tablename__:
                        result = db.execute(delete(table).where(table.c.id == owner_id))
                    else:
                        continue
                    if result.rowcount and result.rowcount > 0:
                        deleted_rows += result.rowcount
                db.commit()

            deleted_raw_files = sum(self._delete_upload_file(path) for path in raw_paths)
            deleted_raw_files += self._purge_directory("uploads")
            deleted_log_files = self._purge_directory("logs")
            deleted_backup_files = purge_sqlite_backups(self.settings.data_dir)
            if self.engine.url.get_backend_name() == "sqlite":
                with self.engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as connection:
                    connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
                    connection.exec_driver_sql("VACUUM")
            return DeleteAllResponse(
                deleted_rows=deleted_rows,
                deleted_raw_files=deleted_raw_files,
                deleted_backup_files=deleted_backup_files,
                deleted_log_files=deleted_log_files,
            )

    def _purge_directory(self, name: str) -> int:
        directory = (self.settings.data_dir / name).resolve()
        if not directory.is_dir():
            return 0
        removed = 0
        for path in directory.iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            path.unlink(missing_ok=True)
            removed += 1
        return removed

    def _delete_upload_file(self, path_value: str | None) -> bool:
        """Delete only regular files confined to this service's upload root."""

        if not path_value:
            return False
        uploads_root = (self.settings.data_dir / "uploads").resolve()
        try:
            path = Path(path_value).resolve()
            path.relative_to(uploads_root)
        except (OSError, ValueError):
            return False
        if not path.is_file() or path.is_symlink():
            return False
        try:
            path.unlink()
        except OSError:
            return False
        return True
