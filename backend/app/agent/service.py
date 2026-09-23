"""Owner-scoped persistence and lifecycle management for Single-Agent runs."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.agent.contracts import AgentExecutionResult
from app.agent.single_agent import SingleAgent
from app.core.config import Settings, get_settings
from app.llm.contracts import CancellationToken
from app.llm.provider import ModelProvider
from app.models.agent import AgentRun, AgentSession, ModelCallTrace
from app.schemas.agent import (
    AgentComparisonResponse,
    AgentMetrics,
    AgentRunResponse,
    AgentSessionListResponse,
    AgentSessionResponse,
    AgentSessionSummary,
    AgentStepTraceResponse,
    ModelCallTraceResponse,
)
from app.services.import_service import ensure_owner
from app.tools.contracts import OwnerContext
from app.tools.runtime import ToolExecutor

SessionFactory = Callable[[], Session]


class AgentRunner(Protocol):
    def run(
        self,
        run_id: str,
        user_query: str,
        context: OwnerContext,
        cancellation_token: CancellationToken | None = None,
    ) -> AgentExecutionResult: ...


AgentFactory = Callable[[], AgentRunner]
_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "needs_confirmation"}
_PLANNER_MARKERS = ("预算", "规划", "计划", "并行", "重新规划", "分歧")
_COMPLEX_MARKERS = (
    "分析",
    "为什么",
    "原因",
    "异常",
    "对比",
    "比较",
    "环比",
    "同比",
    "趋势",
    "建议",
    "综合",
)


class AgentServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ActiveRunRegistry:
    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = Lock()

    def register(self, run_id: str, token: CancellationToken) -> None:
        with self._lock:
            self._tokens[run_id] = token

    def unregister(self, run_id: str) -> None:
        with self._lock:
            self._tokens.pop(run_id, None)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            token = self._tokens.get(run_id)
        if token is None:
            return False
        token.cancel()
        return True


active_runs = ActiveRunRegistry()


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _load_json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _load_json_dict(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _model_call_response(item: ModelCallTrace) -> ModelCallTraceResponse:
    return ModelCallTraceResponse(
        sequence=item.sequence,
        status=item.status,
        provider=item.provider,
        model=item.model,
        latency_ms=item.latency_ms,
        prompt_tokens=item.prompt_tokens,
        completion_tokens=item.completion_tokens,
        total_tokens=item.total_tokens,
        selected_tools=_load_json_list(item.selected_tools_json),
        error_code=item.error_code,
        created_at=_aware(item.created_at),
    )


def run_response(item: AgentRun, *, include_model_calls: bool = True) -> AgentRunResponse:
    model_calls = item.model_calls if include_model_calls else []
    return AgentRunResponse(
        id=item.id,
        session_id=item.session_id,
        status=item.status,
        user_query=item.user_query,
        answer=item.answer,
        error_code=item.error_code,
        error_message=item.error_message,
        provider=item.provider,
        model=item.model,
        workflow=item.workflow,
        evidence_refs=_load_json_list(item.evidence_refs_json),
        tool_names=_load_json_list(item.tool_names_json),
        metrics=AgentMetrics(
            step_count=item.step_count,
            tool_call_count=item.tool_call_count,
            model_call_count=item.model_call_count,
            prompt_tokens=item.prompt_tokens,
            completion_tokens=item.completion_tokens,
            total_tokens=item.total_tokens,
            estimated_cost_microusd=item.estimated_cost_microusd,
            duration_ms=item.duration_ms,
        ),
        cancellation_requested=item.cancellation_requested,
        started_at=_aware(item.started_at),
        completed_at=_aware(item.completed_at),
        model_calls=[_model_call_response(call) for call in model_calls],
        agent_steps=[
            AgentStepTraceResponse(
                sequence=step.sequence,
                node=step.node,
                status=step.status,
                input_summary=_load_json_dict(step.input_summary_json),
                output_summary=_load_json_dict(step.output_summary_json),
                duration_ms=step.duration_ms,
                error_code=step.error_code,
                created_at=_aware(step.created_at),
            )
            for step in item.agent_steps
        ],
    )


class AgentService:
    def __init__(
        self,
        session_factory: SessionFactory,
        provider: ModelProvider,
        tool_executor: ToolExecutor,
        *,
        settings: Settings | None = None,
        run_registry: ActiveRunRegistry = active_runs,
        multi_agent_factory: AgentFactory | None = None,
        planner_agent_factory: AgentFactory | None = None,
        unverified_multi_agent_factory: AgentFactory | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.provider = provider
        self.tool_executor = tool_executor
        self.settings = settings or get_settings()
        self.run_registry = run_registry
        self.multi_agent_factory = multi_agent_factory
        self.planner_agent_factory = planner_agent_factory
        self.unverified_multi_agent_factory = unverified_multi_agent_factory

    def chat(
        self,
        owner_id: str,
        message: str,
        session_id: str | None = None,
        *,
        workflow: str = "auto",
    ) -> AgentRunResponse:
        selected_workflow = self._select_workflow(message, workflow)
        now = datetime.now(UTC)
        with self.session_factory() as db:
            ensure_owner(db, owner_id)
            session = self._get_or_create_session(db, owner_id, message, session_id, now)
            run = AgentRun(
                id=str(uuid4()),
                session_id=session.id,
                owner_id=owner_id,
                status="running",
                user_query=message,
                provider=self.provider.provider,
                model=self.provider.model,
                workflow=selected_workflow,
                started_at=now,
                updated_at=now,
            )
            db.add(run)
            db.commit()
            run_id = run.id

        token = CancellationToken()
        self.run_registry.register(run_id, token)
        if selected_workflow == "planner" and self.planner_agent_factory is not None:
            agent = self.planner_agent_factory()
        elif (
            selected_workflow == "multi_unverified"
            and self.unverified_multi_agent_factory is not None
        ):
            agent = self.unverified_multi_agent_factory()
        elif selected_workflow == "multi" and self.multi_agent_factory is not None:
            agent = self.multi_agent_factory()
        else:
            agent = SingleAgent(
                self.provider,
                self.tool_executor,
                self.session_factory,
                settings=self.settings,
            )
        try:
            result = agent.run(run_id, message, OwnerContext(owner_id=owner_id), token)
        except Exception:
            # Do not persist exception text, model context, or source rows.
            result_status = "failed"
            result_answer = "无法确定：Agent 执行失败。"
            result_code = "AGENT_EXECUTION_ERROR"
            result_message = "Agent 执行失败"
            result_values = {
                "step_count": 0,
                "tool_call_count": 0,
                "model_call_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_microusd": 0,
                "duration_ms": 0,
                "evidence_refs": [],
                "tool_names": [],
            }
        else:
            result_status = result.status
            result_answer = result.answer
            result_code = result.error_code
            result_message = result.error_message
            result_values = result.model_dump(
                include={
                    "step_count",
                    "tool_call_count",
                    "model_call_count",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "estimated_cost_microusd",
                    "duration_ms",
                    "evidence_refs",
                    "tool_names",
                }
            )
        finally:
            self.run_registry.unregister(run_id)

        with self.session_factory() as db:
            run = db.scalar(
                select(AgentRun)
                .options(
                    selectinload(AgentRun.model_calls),
                    selectinload(AgentRun.agent_steps),
                )
                .where(AgentRun.id == run_id, AgentRun.owner_id == owner_id)
            )
            if run is None:
                raise RuntimeError("Agent run disappeared")
            run.status = result_status
            run.answer = result_answer
            run.error_code = result_code
            run.error_message = result_message
            run.step_count = result_values["step_count"]
            run.tool_call_count = result_values["tool_call_count"]
            run.model_call_count = result_values["model_call_count"]
            run.prompt_tokens = result_values["prompt_tokens"]
            run.completion_tokens = result_values["completion_tokens"]
            run.total_tokens = result_values["total_tokens"]
            run.estimated_cost_microusd = result_values["estimated_cost_microusd"]
            run.duration_ms = result_values["duration_ms"]
            run.evidence_refs_json = json.dumps(
                result_values["evidence_refs"], ensure_ascii=False, separators=(",", ":")
            )
            run.tool_names_json = json.dumps(
                result_values["tool_names"], ensure_ascii=False, separators=(",", ":")
            )
            run.completed_at = datetime.now(UTC)
            run.updated_at = run.completed_at
            run.session.updated_at = run.completed_at
            db.commit()
            db.refresh(run)
            return run_response(run)

    def list_sessions(self, owner_id: str, page: int, page_size: int) -> AgentSessionListResponse:
        query = select(AgentSession).where(AgentSession.owner_id == owner_id)
        with self.session_factory() as db:
            total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
            sessions = list(
                db.scalars(
                    query.order_by(AgentSession.updated_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            items = [
                AgentSessionSummary(
                    id=item.id,
                    title=item.title,
                    created_at=_aware(item.created_at),
                    updated_at=_aware(item.updated_at),
                    run_count=(
                        db.scalar(
                            select(func.count())
                            .select_from(AgentRun)
                            .where(AgentRun.session_id == item.id, AgentRun.owner_id == owner_id)
                        )
                        or 0
                    ),
                )
                for item in sessions
            ]
        return AgentSessionListResponse(items=items, total=total, page=page, page_size=page_size)

    def get_session(self, owner_id: str, session_id: str) -> AgentSessionResponse | None:
        with self.session_factory() as db:
            item = db.scalar(
                select(AgentSession)
                .options(
                    selectinload(AgentSession.runs).selectinload(AgentRun.model_calls),
                    selectinload(AgentSession.runs).selectinload(AgentRun.agent_steps),
                )
                .where(AgentSession.id == session_id, AgentSession.owner_id == owner_id)
            )
            if item is None:
                return None
            return AgentSessionResponse(
                id=item.id,
                title=item.title,
                created_at=_aware(item.created_at),
                updated_at=_aware(item.updated_at),
                run_count=len(item.runs),
                runs=[run_response(run) for run in item.runs],
            )

    def get_run(self, owner_id: str, run_id: str) -> AgentRunResponse | None:
        with self.session_factory() as db:
            item = db.scalar(
                select(AgentRun)
                .options(
                    selectinload(AgentRun.model_calls),
                    selectinload(AgentRun.agent_steps),
                )
                .where(AgentRun.id == run_id, AgentRun.owner_id == owner_id)
            )
            return run_response(item) if item is not None else None

    def cancel_run(self, owner_id: str, run_id: str) -> AgentRunResponse | None:
        with self.session_factory() as db:
            item = db.scalar(
                select(AgentRun)
                .options(
                    selectinload(AgentRun.model_calls),
                    selectinload(AgentRun.agent_steps),
                )
                .where(AgentRun.id == run_id, AgentRun.owner_id == owner_id)
            )
            if item is None:
                return None
            if item.status in _TERMINAL_STATUSES:
                return run_response(item)
            item.cancellation_requested = True
            if not self.run_registry.cancel(run_id):
                item.status = "cancelled"
                item.error_code = "MODEL_CANCELLED"
                item.error_message = "Agent 运行已取消"
                item.answer = "无法确定：Agent 运行已取消。"
                item.completed_at = datetime.now(UTC)
            item.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(item)
            return run_response(item)

    def compare(self, owner_id: str, message: str) -> AgentComparisonResponse:
        if self.multi_agent_factory is None:
            raise AgentServiceError("MULTI_AGENT_UNAVAILABLE", "Multi-Agent 运行时未启用")
        single = self.chat(owner_id, message, workflow="single")
        multi = self.chat(owner_id, message, workflow="multi")
        context = OwnerContext(owner_id=owner_id)

        def evidence_signatures(evidence_refs: list[str]) -> set[str]:
            signatures: set[str] = set()
            for evidence_id in evidence_refs:
                evidence = self.tool_executor.replay(evidence_id, context)
                if evidence is None:
                    continue
                signatures.add(
                    json.dumps(
                        {"tool_name": evidence.tool_name, "data": evidence.data},
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            return signatures

        shared_evidence = evidence_signatures(single.evidence_refs) & evidence_signatures(
            multi.evidence_refs
        )
        return AgentComparisonResponse(
            single=single,
            multi=multi,
            same_status=single.status == multi.status,
            same_tools=single.tool_names == multi.tool_names,
            shared_evidence_count=len(shared_evidence),
            latency_delta_ms=multi.metrics.duration_ms - single.metrics.duration_ms,
            token_delta=multi.metrics.total_tokens - single.metrics.total_tokens,
        )

    def _select_workflow(self, message: str, workflow: str) -> str:
        if workflow not in {"auto", "single", "multi", "multi_unverified", "planner"}:
            raise AgentServiceError("INVALID_WORKFLOW", "Agent 工作流模式无效")
        if workflow == "single":
            return "single"
        if workflow == "multi":
            if self.multi_agent_factory is None:
                raise AgentServiceError("MULTI_AGENT_UNAVAILABLE", "Multi-Agent 运行时未启用")
            return "multi"
        if workflow == "planner":
            if self.planner_agent_factory is None:
                raise AgentServiceError("PLANNER_UNAVAILABLE", "Planner 运行时未启用")
            return "planner"
        if workflow == "multi_unverified":
            if self.unverified_multi_agent_factory is None:
                raise AgentServiceError(
                    "MULTI_AGENT_UNAVAILABLE", "无 Verifier 的 Multi-Agent 运行时未启用"
                )
            return "multi_unverified"
        if any(marker in message for marker in _PLANNER_MARKERS):
            if self.planner_agent_factory is not None:
                return "planner"
        is_complex = any(marker in message for marker in _COMPLEX_MARKERS)
        return "multi" if is_complex and self.multi_agent_factory is not None else "single"

    @staticmethod
    def _get_or_create_session(
        db: Session,
        owner_id: str,
        message: str,
        session_id: str | None,
        now: datetime,
    ) -> AgentSession:
        if session_id:
            item = db.scalar(
                select(AgentSession).where(
                    AgentSession.id == session_id,
                    AgentSession.owner_id == owner_id,
                )
            )
            if item is None:
                raise AgentServiceError("AGENT_SESSION_NOT_FOUND", "Agent 会话不存在")
            return item
        title = " ".join(message.split())[:120] or "新对话"
        item = AgentSession(
            id=str(uuid4()),
            owner_id=owner_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        db.add(item)
        db.flush()
        return item
