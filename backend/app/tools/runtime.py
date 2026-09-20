"""Bounded execution, tracing, and owner-scoped evidence replay for Tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.tooling import ToolTrace
from app.services.import_service import ensure_owner
from app.services.stats_service import StatsServiceError
from app.tools.contracts import OwnerContext, ToolError, ToolExecutionResult
from app.tools.registry import ToolDefinition, ToolRegistry, readonly_tool_registry

SessionFactory = Callable[[], Session]


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    raise TypeError(f"不支持的 JSON 类型: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _duration_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _validation_details(exc: ValidationError) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for error in exc.errors(include_input=False, include_context=False):
        location = ".".join(str(part) for part in error.get("loc", ())) or "arguments"
        details.append({"field": location, "message": str(error.get("msg", "参数无效"))})
    return details


class EvidenceIntegrityError(RuntimeError):
    """Raised when a persisted evidence snapshot no longer matches its digest."""


class ToolExecutor:
    """Execute registered read-only Tools without exposing owner selection.

    Each handler receives a fresh database Session created inside the worker
    thread. A timed-out read may finish in the background, but its result is
    discarded and the persisted trace remains a timeout error.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        registry: ToolRegistry = readonly_tool_registry,
        timeout_seconds: float | None = None,
        max_result_bytes: int | None = None,
        max_workers: int = 4,
    ) -> None:
        self.session_factory = session_factory
        self.registry = registry
        self.timeout_seconds = (
            get_settings().tool_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        if self.timeout_seconds <= 0:
            raise ValueError("Tool 超时必须大于 0")
        self.max_result_bytes = (
            get_settings().tool_max_result_bytes if max_result_bytes is None else max_result_bytes
        )
        if self.max_result_bytes < 1024:
            raise ValueError("Tool 结果大小上限不能小于 1024 字节")
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pfa-tool")

    def __enter__(self) -> ToolExecutor:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def close(self, *, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=True)

    def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        context: OwnerContext,
        *,
        run_id: str | None = None,
    ) -> ToolExecutionResult:
        started_clock = monotonic()
        started_at = datetime.now(UTC)
        evidence_id = f"ev_{uuid4().hex}"
        self._ensure_owner(context.owner_id)
        definition = self.registry.get(tool_name)

        if definition is None:
            result = self._error_result(
                evidence_id,
                tool_name,
                started_at,
                started_clock,
                "UNKNOWN_TOOL",
                "请求的 Tool 不存在",
            )
            self._persist_trace(context, {}, result, run_id)
            return result

        try:
            validated = definition.arguments_model.model_validate(dict(arguments))
        except ValidationError as exc:
            result = self._error_result(
                evidence_id,
                tool_name,
                started_at,
                started_clock,
                "INVALID_ARGUMENTS",
                "Tool 参数未通过 Schema 校验",
                _validation_details(exc),
                definition.contract_version,
            )
            self._persist_trace(
                context,
                self._safe_invalid_arguments(definition, arguments),
                result,
                run_id,
            )
            return result

        persisted_arguments = validated.model_dump(mode="json", by_alias=True)
        future = self._pool.submit(self._invoke, definition, context, validated)
        try:
            data = future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            result = self._error_result(
                evidence_id,
                tool_name,
                started_at,
                started_clock,
                "TOOL_TIMEOUT",
                "Tool 执行超过时间限制",
                contract_version=definition.contract_version,
            )
        except (StatsServiceError, ValueError) as exc:
            result = self._error_result(
                evidence_id,
                tool_name,
                started_at,
                started_clock,
                "TOOL_VALIDATION_ERROR",
                str(exc),
                contract_version=definition.contract_version,
            )
        except Exception:
            # Do not expose SQL, paths, driver details, or source rows.
            result = self._error_result(
                evidence_id,
                tool_name,
                started_at,
                started_clock,
                "TOOL_EXECUTION_ERROR",
                "Tool 执行失败",
                contract_version=definition.contract_version,
            )
        else:
            if len(_canonical_json(data).encode("utf-8")) > self.max_result_bytes:
                result = self._error_result(
                    evidence_id,
                    tool_name,
                    started_at,
                    started_clock,
                    "TOOL_RESULT_TOO_LARGE",
                    "Tool 结果超过大小限制，请缩短周期或收紧筛选条件",
                    contract_version=definition.contract_version,
                )
            else:
                completed_at = datetime.now(UTC)
                result = ToolExecutionResult(
                    evidence_id=evidence_id,
                    tool_name=tool_name,
                    contract_version=definition.contract_version,
                    status="success",
                    data=data,
                    methodology=definition.methodology(),
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=_duration_ms(started_clock),
                )

        self._persist_trace(context, persisted_arguments, result, run_id)
        return result

    def replay(self, evidence_id: str, context: OwnerContext) -> ToolExecutionResult | None:
        """Return the immutable snapshot for evidence owned by this context."""

        with self.session_factory() as db:
            trace = db.scalar(
                select(ToolTrace).where(
                    ToolTrace.evidence_id == evidence_id,
                    ToolTrace.owner_id == context.owner_id,
                )
            )
            if trace is None:
                return None
            if _sha256(trace.result_json) != trace.result_sha256:
                raise EvidenceIntegrityError("evidence 快照完整性校验失败")
            result = ToolExecutionResult.model_validate_json(trace.result_json)
            return result.model_copy(update={"replayed": True})

    def _invoke(
        self,
        definition: ToolDefinition,
        context: OwnerContext,
        arguments: BaseModel,
    ) -> dict[str, Any]:
        with self.session_factory() as db:
            output = definition.handler(db, context, arguments)
            if isinstance(output, BaseModel):
                return output.model_dump(mode="json")
            return output

    def _ensure_owner(self, owner_id: str) -> None:
        with self.session_factory() as db:
            ensure_owner(db, owner_id)

    def _persist_trace(
        self,
        context: OwnerContext,
        arguments: Mapping[str, Any],
        result: ToolExecutionResult,
        run_id: str | None,
    ) -> None:
        arguments_json = _canonical_json(dict(arguments))
        result_json = _canonical_json(result.model_dump(mode="json"))
        with self.session_factory() as db:
            db.add(
                ToolTrace(
                    evidence_id=result.evidence_id,
                    owner_id=context.owner_id,
                    run_id=run_id,
                    tool_name=result.tool_name[:64],
                    contract_version=result.contract_version,
                    status=result.status,
                    arguments_json=arguments_json,
                    arguments_sha256=_sha256(arguments_json),
                    result_json=result_json,
                    result_sha256=_sha256(result_json),
                    error_code=result.error.code if result.error else None,
                    started_at=result.started_at,
                    completed_at=result.completed_at,
                    duration_ms=result.duration_ms,
                )
            )
            db.commit()

    @staticmethod
    def _safe_invalid_arguments(
        definition: ToolDefinition, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        # Persist values only for declared fields. Unknown keys may contain an
        # attempted owner override, arbitrary prompt content, or secrets.
        aliases = {
            field.alias or name for name, field in definition.arguments_model.model_fields.items()
        }
        return {
            key: ToolExecutor._safe_trace_value(value)
            for key, value in arguments.items()
            if key in aliases
        }

    @staticmethod
    def _safe_trace_value(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return value[:256]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (list, tuple)):
            return [ToolExecutor._safe_trace_value(item) for item in value[:20]]
        if isinstance(value, Mapping):
            return {
                str(key)[:64]: ToolExecutor._safe_trace_value(item)
                for key, item in list(value.items())[:20]
            }
        return f"<{type(value).__name__}>"

    @staticmethod
    def _error_result(
        evidence_id: str,
        tool_name: str,
        started_at: datetime,
        started_clock: float,
        code: str,
        message: str,
        details: list[dict[str, str]] | None = None,
        contract_version: str = "1.0",
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            evidence_id=evidence_id,
            tool_name=tool_name,
            contract_version=contract_version,
            status="error",
            error=ToolError(code=code, message=message, details=details or []),
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=_duration_ms(started_clock),
        )
