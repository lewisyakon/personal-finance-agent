"""User-confirmed, versioned, expiring memories with explainable retrieval."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.models.memory import MemoryAccessTrace, MemoryRecord
from app.models.semantic import MerchantRule
from app.schemas.memory import (
    MemoryAccessListResponse,
    MemoryAccessResponse,
    MemoryContext,
    MemoryListResponse,
    MemoryResponse,
)
from app.services.import_service import ensure_owner
from app.services.semantic_service import normalize_merchant


class MemoryServiceError(ValueError):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def memory_response(item: MemoryRecord) -> MemoryResponse:
    return MemoryResponse(
        id=item.id,
        scope=item.scope,
        kind=item.kind,
        key=item.memory_key,
        value=_json_dict(item.value_json),
        source=item.source,
        source_ref_type=item.source_ref_type,
        source_ref_id=item.source_ref_id,
        status=item.status,
        version=item.version,
        supersedes_id=item.supersedes_id,
        expires_at=_aware(item.expires_at),
        created_at=_aware(item.created_at),
        updated_at=_aware(item.updated_at),
    )


class MemoryService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def remember(
        self,
        owner_id: str,
        scope: str,
        kind: str,
        key: str,
        value: dict[str, Any],
        *,
        expires_at: datetime | None = None,
        source_ref_type: str | None = None,
        source_ref_id: str | None = None,
    ) -> MemoryResponse:
        if scope not in {"session", "long_term", "knowledge"}:
            raise MemoryServiceError("INVALID_MEMORY_SCOPE", "记忆范围无效")
        normalized_key = key.strip()
        if not normalized_key:
            raise MemoryServiceError("INVALID_MEMORY_KEY", "记忆 Key 不能为空")
        if expires_at is not None and expires_at <= datetime.now(UTC):
            raise MemoryServiceError("INVALID_MEMORY_EXPIRY", "记忆过期时间必须晚于当前时间")
        if scope == "session" and expires_at is None:
            expires_at = datetime.now(UTC) + timedelta(hours=24)
        session_id = value.get("session_id")
        if scope == "session" and not (
            isinstance(session_id, str) and session_id.strip()
        ):
            raise MemoryServiceError(
                "SESSION_MEMORY_REQUIRES_SESSION_ID",
                "会话记忆必须包含 session_id",
            )
        value_json = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(value_json.encode("utf-8")) > 8192:
            raise MemoryServiceError("MEMORY_VALUE_TOO_LARGE", "记忆内容超过 8 KiB")
        now = datetime.now(UTC)
        with self.session_factory() as db:
            ensure_owner(db, owner_id)
            current = db.scalar(
                select(MemoryRecord)
                .where(
                    MemoryRecord.owner_id == owner_id,
                    MemoryRecord.scope == scope,
                    MemoryRecord.kind == kind,
                    MemoryRecord.memory_key == normalized_key,
                    MemoryRecord.status == "active",
                )
                .order_by(MemoryRecord.version.desc())
            )
            if (
                current is not None
                and current.value_json == value_json
                and _aware(current.expires_at) == expires_at
                and current.source_ref_type == source_ref_type
                and current.source_ref_id == source_ref_id
            ):
                return memory_response(current)
            version = 1
            supersedes_id = None
            if current is not None:
                current.status = "superseded"
                current.updated_at = now
                version = current.version + 1
                supersedes_id = current.id
            item = MemoryRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                scope=scope,
                kind=kind,
                memory_key=normalized_key,
                value_json=value_json,
                source="user_confirmed",
                source_ref_type=source_ref_type,
                source_ref_id=source_ref_id,
                status="active",
                version=version,
                supersedes_id=supersedes_id,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            return memory_response(item)

    def list(self, owner_id: str, scope: str | None = None) -> MemoryListResponse:
        now = datetime.now(UTC)
        with self.session_factory() as db:
            self._expire(db, owner_id, now)
            query = select(MemoryRecord).where(
                MemoryRecord.owner_id == owner_id,
                MemoryRecord.status == "active",
            )
            if scope is not None:
                query = query.where(MemoryRecord.scope == scope)
            items = list(db.scalars(query.order_by(MemoryRecord.updated_at.desc())))
            db.commit()
        return MemoryListResponse(items=[memory_response(item) for item in items], total=len(items))

    def update(
        self,
        owner_id: str,
        memory_id: str,
        value: dict[str, Any] | None,
        expires_at: datetime | None,
    ) -> MemoryResponse:
        with self.session_factory() as db:
            item = self._memory(db, owner_id, memory_id)
            current_value = _json_dict(item.value_json)
            scope = item.scope
            kind = item.kind
            key = item.memory_key
            source_ref_type = item.source_ref_type
            source_ref_id = item.source_ref_id
            current_expiry = _aware(item.expires_at)
        return self.remember(
            owner_id,
            scope,
            kind,
            key,
            value if value is not None else current_value,
            expires_at=expires_at if expires_at is not None else current_expiry,
            source_ref_type=source_ref_type,
            source_ref_id=source_ref_id,
        )

    def delete(self, owner_id: str, memory_id: str) -> bool:
        with self.session_factory() as db:
            item = db.scalar(
                select(MemoryRecord).where(
                    MemoryRecord.id == memory_id,
                    MemoryRecord.owner_id == owner_id,
                )
            )
            if item is None:
                return False
            now = datetime.now(UTC)
            item.status = "deleted"
            item.deleted_at = now
            item.updated_at = now
            if item.source_ref_type == "merchant_rule" and item.source_ref_id:
                rule = db.scalar(
                    select(MerchantRule).where(
                        MerchantRule.id == item.source_ref_id,
                        MerchantRule.owner_id == owner_id,
                    )
                )
                if rule is not None:
                    rule.active = False
                    rule.updated_at = now
            db.commit()
            return True

    def delete_by_source(self, owner_id: str, source_ref_type: str, source_ref_id: str) -> int:
        now = datetime.now(UTC)
        with self.session_factory() as db:
            items = list(
                db.scalars(
                    select(MemoryRecord).where(
                        MemoryRecord.owner_id == owner_id,
                        MemoryRecord.source_ref_type == source_ref_type,
                        MemoryRecord.source_ref_id == source_ref_id,
                        MemoryRecord.status == "active",
                    )
                )
            )
            for item in items:
                item.status = "deleted"
                item.deleted_at = now
                item.updated_at = now
            db.commit()
            return len(items)

    def retrieve(
        self,
        owner_id: str,
        query: str,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> MemoryContext:
        now = datetime.now(UTC)
        query_folded = query.casefold()
        normalized_query = normalize_merchant(query)
        with self.session_factory() as db:
            self._expire(db, owner_id, now)
            candidates = list(
                db.scalars(
                    select(MemoryRecord).where(
                        MemoryRecord.owner_id == owner_id,
                        MemoryRecord.status == "active",
                    )
                )
            )
            matches: list[MemoryRecord] = []
            for item in candidates:
                value = _json_dict(item.value_json)
                if item.scope == "session" and value.get("session_id") != session_id:
                    continue
                key_folded = item.memory_key.casefold()
                normalized_key = normalize_merchant(item.memory_key)
                matched = (
                    key_folded in query_folded
                    or bool(normalized_key and normalized_key in normalized_query)
                )
                if item.kind == "budget_preference" and "预算" in query:
                    matched = True
                if matched:
                    matches.append(item)
            matches.sort(key=lambda item: (item.scope, item.kind, item.memory_key))
            trace = MemoryAccessTrace(
                id=str(uuid4()),
                owner_id=owner_id,
                run_id=run_id,
                query_fingerprint=hashlib.sha256(query.encode("utf-8")).hexdigest(),
                status="hit" if matches else "miss",
                matched_memory_ids_json=json.dumps(
                    [item.id for item in matches], separators=(",", ":")
                ),
                reason=(
                    "matched_active_user_confirmed_memory"
                    if matches
                    else "no_active_unexpired_match"
                ),
                created_at=now,
            )
            db.add(trace)
            db.commit()
            return MemoryContext(
                status=trace.status,
                items=[memory_response(item) for item in matches],
                reason=trace.reason,
            )

    def list_accesses(self, owner_id: str) -> MemoryAccessListResponse:
        with self.session_factory() as db:
            rows = list(
                db.scalars(
                    select(MemoryAccessTrace)
                    .where(MemoryAccessTrace.owner_id == owner_id)
                    .order_by(MemoryAccessTrace.created_at.desc())
                    .limit(200)
                )
            )
        return MemoryAccessListResponse(
            items=[
                MemoryAccessResponse(
                    id=item.id,
                    run_id=item.run_id,
                    status=item.status,
                    matched_memory_ids=_json_list(item.matched_memory_ids_json),
                    reason=item.reason,
                    created_at=_aware(item.created_at),
                )
                for item in rows
            ],
            total=len(rows),
        )

    @staticmethod
    def _memory(db, owner_id: str, memory_id: str) -> MemoryRecord:
        item = db.scalar(
            select(MemoryRecord).where(
                MemoryRecord.id == memory_id,
                MemoryRecord.owner_id == owner_id,
                MemoryRecord.status == "active",
            )
        )
        if item is None:
            raise MemoryServiceError("MEMORY_NOT_FOUND", "记忆不存在", http_status=404)
        return item

    @staticmethod
    def _expire(db, owner_id: str, now: datetime) -> None:
        rows = list(
            db.scalars(
                select(MemoryRecord).where(
                    MemoryRecord.owner_id == owner_id,
                    MemoryRecord.status == "active",
                    MemoryRecord.expires_at.is_not(None),
                    MemoryRecord.expires_at <= now,
                )
            )
        )
        for item in rows:
            item.status = "expired"
            item.updated_at = now
