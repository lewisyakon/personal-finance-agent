"""Fixed Supervisor -> Analysis -> Verifier LangGraph workflow."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.contracts import AgentExecutionResult
from app.agent.handoffs import AnalysisHandoff, SupervisorHandoff, VerificationResult
from app.agent.registry import AgentRegistry, fixed_agent_registry
from app.agent.single_agent import SingleAgent
from app.agent.verifier import verify_analysis
from app.core.config import Settings, get_settings
from app.llm.contracts import (
    CancellationToken,
    ModelCompletion,
    ModelMessage,
    ModelProviderError,
    ModelRequest,
    StructuredOutputSpec,
)
from app.llm.provider import ModelProvider
from app.models.agent import ModelCallTrace
from app.models.multi_agent import AgentStepTrace
from app.tools.contracts import OwnerContext
from app.tools.registry import ToolRegistry, readonly_tool_registry
from app.tools.runtime import ToolExecutor

SessionFactory = Callable[[], Session]

_SUPERVISOR_PROMPT = """你是固定工作流的 Supervisor。
只负责把用户问题规范化为一个 Analysis 任务，不回答问题、不计算金额。
只能从提供的只读 Tool 名称中选择；日期必须带时区并使用左闭右开范围。
输出必须符合 JSON Schema，不得输出 owner_id、SQL、路径、URL 或思考过程。
"""


class MultiAgentState(TypedDict):
    run_id: str
    owner_id: str
    user_query: str
    normalized_intent: str
    constraints: dict[str, Any]
    plan: list[dict[str, Any]]
    task_results: list[dict[str, Any]]
    statistics: dict[str, Any]
    classification_candidates: list[dict[str, Any]]
    findings: list[str]
    budget_draft: dict[str, Any] | None
    evidence_refs: list[str]
    verification: dict[str, Any]
    errors: list[str]
    status: str
    answer: str
    error_code: str | None
    error_message: str | None
    step_count: int
    tool_call_count: int
    model_call_count: int
    token_usage: dict[str, int]
    tool_names: list[str]
    tool_results: list[dict[str, Any]]
    supervisor_handoff: SupervisorHandoff | None
    analysis_handoff: AnalysisHandoff | None
    started_clock: float


class MultiAgent:
    def __init__(
        self,
        provider: ModelProvider,
        tool_executor: ToolExecutor,
        session_factory: SessionFactory,
        *,
        registry: ToolRegistry = readonly_tool_registry,
        agent_registry: AgentRegistry = fixed_agent_registry,
        settings: Settings | None = None,
        verification_enabled: bool = True,
    ) -> None:
        self.provider = provider
        self.tool_executor = tool_executor
        self.session_factory = session_factory
        self.registry = registry
        self.agent_registry = agent_registry
        self.settings = settings or get_settings()
        self.verification_enabled = verification_enabled
        self._token: CancellationToken | None = None
        self.graph = self._build_graph()

    def run(
        self,
        run_id: str,
        user_query: str,
        context: OwnerContext,
        cancellation_token: CancellationToken | None = None,
    ) -> AgentExecutionResult:
        self._token = cancellation_token or CancellationToken()
        started = monotonic()
        initial: MultiAgentState = {
            "run_id": run_id,
            "owner_id": context.owner_id,
            "user_query": user_query,
            "normalized_intent": "",
            "constraints": {},
            "plan": [],
            "task_results": [],
            "statistics": {},
            "classification_candidates": [],
            "findings": [],
            "budget_draft": None,
            "evidence_refs": [],
            "verification": {},
            "errors": [],
            "status": "running",
            "answer": "",
            "error_code": None,
            "error_message": None,
            "step_count": 0,
            "tool_call_count": 0,
            "model_call_count": 0,
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            "tool_names": [],
            "tool_results": [],
            "supervisor_handoff": None,
            "analysis_handoff": None,
            "started_clock": started,
        }
        final = self.graph.invoke(initial, config={"recursion_limit": 8})
        if final["status"] == "running":
            final.update(
                status="failed",
                answer="无法确定：Multi-Agent 未正常终止。",
                error_code="MULTI_AGENT_TERMINATION_ERROR",
                error_message="Multi-Agent 未正常终止",
            )
        usage = final["token_usage"]
        return AgentExecutionResult(
            run_id=run_id,
            status=final["status"],
            answer=final["answer"],
            error_code=final["error_code"],
            error_message=final["error_message"],
            evidence_refs=final["evidence_refs"],
            tool_names=final["tool_names"],
            tool_results=final["tool_results"],
            step_count=final["step_count"],
            tool_call_count=final["tool_call_count"],
            model_call_count=final["model_call_count"],
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            duration_ms=max(0, round((monotonic() - started) * 1000)),
        )

    def _build_graph(self):
        builder = StateGraph(MultiAgentState)
        builder.add_node("supervisor", self._supervisor)
        builder.add_node("analysis", self._analysis)
        builder.add_node("verifier", self._verifier)
        builder.add_edge(START, "supervisor")
        builder.add_edge("supervisor", "analysis")
        builder.add_edge("analysis", "verifier")
        builder.add_edge("verifier", END)
        return builder.compile()

    def _supervisor(self, state: MultiAgentState) -> dict[str, Any]:
        started = monotonic()
        input_summary = {"query_chars": len(state["user_query"]), "step_count": state["step_count"]}
        token = self._token or CancellationToken()
        completion: ModelCompletion | None = None
        try:
            self._check_runtime(state)
            token.raise_if_cancelled()
            messages = [
                ModelMessage(role="developer", content=_SUPERVISOR_PROMPT),
                ModelMessage(
                    role="developer",
                    content="允许的 Tool："
                    + ",".join(item.name for item in self.registry.definitions()),
                ),
                ModelMessage(role="user", content=state["user_query"]),
            ]
            if sum(len(message.content or "") for message in messages) > (
                self.settings.agent_max_context_chars
            ):
                raise ModelProviderError("AGENT_CONTEXT_LIMIT", "Supervisor 模型上下文超过限制")
            completion = self.provider.complete(
                ModelRequest(
                    run_id=state["run_id"],
                    messages=messages,
                    response_format=StructuredOutputSpec(
                        name="supervisor_handoff",
                        schema=SupervisorHandoff.model_json_schema(),
                    ),
                ),
                token,
            )
            handoff = SupervisorHandoff.model_validate_json(completion.content or "")
            allowed = {item.name for item in self.registry.definitions()}
            selected = {name for task in handoff.plan for name in task.required_tools}
            if not selected.issubset(allowed):
                raise ValueError("Supervisor 选择了未知 Tool")
        except ModelProviderError as exc:
            self._record_model_error(state, 1, exc, started)
            update = self._failure_update(state, exc.code, exc.message)
        except (ValidationError, ValueError):
            update = self._failure_update(
                state,
                "INVALID_SUPERVISOR_HANDOFF",
                "Supervisor Handoff 结构或权限无效",
            )
            if completion is not None:
                self._record_model_invalid(state, 1, completion)
                update["token_usage"] = self._add_usage(state["token_usage"], completion)
        else:
            self._record_model_success(state, 1, completion)
            usage = self._add_usage(state["token_usage"], completion)
            if usage["total_tokens"] > self.settings.agent_max_total_tokens:
                update = self._failure_update(
                    state,
                    "AGENT_TOKEN_LIMIT",
                    "Agent Token 使用超过限制",
                )
                update["token_usage"] = usage
                self.agent_registry.validate_update("supervisor", update)
                self._record_step(
                    state,
                    1,
                    "supervisor",
                    "failed",
                    input_summary,
                    {"plan_count": 0, "error_count": 1},
                    started,
                    update["error_code"],
                )
                return update
            update = {
                "normalized_intent": handoff.normalized_intent,
                "constraints": {
                    "from": handoff.date_from.isoformat(),
                    "to": handoff.date_to.isoformat(),
                    "direction": handoff.direction,
                },
                "plan": [task.model_dump(mode="json") for task in handoff.plan],
                "supervisor_handoff": handoff,
                "step_count": state["step_count"] + 1,
                "model_call_count": state["model_call_count"] + 1,
                "token_usage": usage,
            }
        self.agent_registry.validate_update("supervisor", update)
        self._record_step(
            state,
            1,
            "supervisor",
            "failed" if update.get("errors") else "succeeded",
            input_summary,
            {
                "plan_count": len(update.get("plan", [])),
                "error_count": len(update.get("errors", [])),
            },
            started,
            update.get("error_code"),
        )
        return update

    def _analysis(self, state: MultiAgentState) -> dict[str, Any]:
        started = monotonic()
        if state["errors"] or state["supervisor_handoff"] is None:
            update = {
                "analysis_handoff": AnalysisHandoff(
                    status="failed",
                    answer="无法确定：Supervisor 未生成有效计划。",
                    evidence_refs=[],
                    tool_names=[],
                    tool_results=[],
                    error_code="SUPERVISOR_FAILED",
                    error_message="Supervisor 未生成有效计划",
                ),
                "task_results": [],
                "statistics": {},
                "findings": [],
                "evidence_refs": [],
                "status": "failed",
                "answer": "无法确定：Supervisor 未生成有效计划。",
                "error_code": "SUPERVISOR_FAILED",
                "error_message": "Supervisor 未生成有效计划",
                "step_count": state["step_count"] + 1,
            }
        else:
            context = json.dumps(
                {
                    "normalized_intent": state["normalized_intent"],
                    "constraints": state["constraints"],
                    "plan": state["plan"],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            single = SingleAgent(
                self.provider,
                self.tool_executor,
                self.session_factory,
                registry=self.registry,
                settings=self.settings,
            )
            result = single.run(
                state["run_id"],
                state["user_query"],
                OwnerContext(owner_id=state["owner_id"]),
                self._token,
                initial_step_count=state["step_count"],
                initial_model_call_count=state["model_call_count"],
                initial_prompt_tokens=state["token_usage"]["prompt_tokens"],
                initial_completion_tokens=state["token_usage"]["completion_tokens"],
                initial_total_tokens=state["token_usage"]["total_tokens"],
                started_clock=state["started_clock"],
                analysis_context="Supervisor 的结构化 Handoff：" + context,
            )
            handoff = AnalysisHandoff(
                status=result.status,
                answer=result.answer,
                evidence_refs=result.evidence_refs,
                tool_names=result.tool_names,
                tool_results=result.tool_results,
                error_code=result.error_code,
                error_message=result.error_message,
            )
            update = {
                "analysis_handoff": handoff,
                "task_results": [
                    {
                        "task_id": state["plan"][0]["task_id"],
                        "status": result.status,
                        "evidence_count": len(result.evidence_refs),
                    }
                ],
                "statistics": {
                    "model_call_count": result.model_call_count,
                    "tool_call_count": result.tool_call_count,
                },
                "findings": ["analysis_answer_ready"] if result.status == "succeeded" else [],
                "evidence_refs": result.evidence_refs,
                "tool_names": result.tool_names,
                "tool_results": result.tool_results,
                "status": result.status,
                "answer": result.answer,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "errors": (
                    state["errors"]
                    if result.status == "succeeded"
                    else [*state["errors"], result.error_code or "ANALYSIS_FAILED"]
                ),
                "step_count": result.step_count,
                "tool_call_count": result.tool_call_count,
                "model_call_count": result.model_call_count,
                "token_usage": {
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "total_tokens": result.total_tokens,
                },
            }
        self.agent_registry.validate_update("analysis", update)
        self._record_step(
            state,
            2,
            "analysis",
            "succeeded" if update.get("status") == "succeeded" else "failed",
            {"plan_count": len(state["plan"]), "prior_error_count": len(state["errors"])},
            {
                "evidence_count": len(update.get("evidence_refs", [])),
                "tool_call_count": update.get("tool_call_count", 0),
            },
            started,
            update.get("error_code"),
        )
        return update

    def _verifier(self, state: MultiAgentState) -> dict[str, Any]:
        started = monotonic()
        if not self.verification_enabled:
            passed = state["status"] == "succeeded"
            update = {
                "verification": {
                    "passed": passed,
                    "issues": [],
                    "checked_evidence_count": 0,
                    "skipped": True,
                },
                "status": state["status"],
                "answer": state["answer"],
                "error_code": state["error_code"],
                "error_message": state["error_message"],
                "errors": state["errors"],
                "step_count": state["step_count"] + 1,
            }
            self.agent_registry.validate_update("verifier", update)
            self._record_step(
                state,
                3,
                "verifier",
                "skipped",
                {
                    "evidence_count": len(state["evidence_refs"]),
                    "tool_count": len(state["tool_names"]),
                },
                {"passed": passed, "issue_codes": [], "skipped": True},
                started,
                update["error_code"],
            )
            return update
        supervisor = state["supervisor_handoff"]
        analysis = state["analysis_handoff"]
        if supervisor is None or analysis is None:
            verification = VerificationResult(
                passed=False,
                issues=[],
                checked_evidence_count=0,
            )
            error_message = "缺少结构化 Handoff，Verifier 无法验证"
        else:
            verification = verify_analysis(supervisor, analysis)
            error_message = (
                "；".join(item.message for item in verification.issues)
                if verification.issues
                else None
            )
        passed = verification.passed
        evidence_line = "、".join(state["evidence_refs"])
        answer = state["answer"]
        if passed and evidence_line and "证据：" not in answer:
            answer = f"{answer}\n\n证据：{evidence_line}"
        if not passed:
            answer = f"无法确定：{error_message or 'Verifier 验证失败'}。"
        update = {
            "verification": verification.model_dump(mode="json"),
            "status": "succeeded" if passed else "failed",
            "answer": answer,
            "error_code": None if passed else "VERIFICATION_FAILED",
            "error_message": None if passed else error_message,
            "errors": (
                state["errors"]
                if passed
                else [*state["errors"], *(item.code for item in verification.issues)]
            ),
            "step_count": state["step_count"] + 1,
        }
        self.agent_registry.validate_update("verifier", update)
        self._record_step(
            state,
            3,
            "verifier",
            "succeeded" if passed else "failed",
            {
                "evidence_count": len(state["evidence_refs"]),
                "tool_count": len(state["tool_names"]),
            },
            {
                "passed": passed,
                "issue_codes": [item.code for item in verification.issues],
            },
            started,
            update["error_code"],
        )
        return update

    def _check_runtime(self, state: MultiAgentState) -> None:
        if monotonic() - state["started_clock"] >= self.settings.agent_total_timeout_seconds:
            raise ModelProviderError("AGENT_TIMEOUT", "Agent 总运行时间超过限制")
        if state["step_count"] >= self.settings.agent_max_steps:
            raise ModelProviderError("AGENT_STEP_LIMIT", "Agent 步数超过限制")
        if state["model_call_count"] >= self.settings.agent_max_model_calls:
            raise ModelProviderError("AGENT_MODEL_LIMIT", "模型调用次数超过限制")

    @staticmethod
    def _add_usage(current: dict[str, int], completion: ModelCompletion) -> dict[str, int]:
        return {
            "prompt_tokens": current["prompt_tokens"] + completion.usage.prompt_tokens,
            "completion_tokens": current["completion_tokens"] + completion.usage.completion_tokens,
            "total_tokens": current["total_tokens"] + completion.usage.total_tokens,
        }

    @staticmethod
    def _failure_update(state: MultiAgentState, code: str, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "answer": f"无法确定：{message}。",
            "error_code": code,
            "error_message": message,
            "errors": [*state["errors"], code],
            "step_count": state["step_count"] + 1,
            "model_call_count": state["model_call_count"] + 1,
        }

    def _record_model_success(
        self, state: MultiAgentState, sequence: int, completion: ModelCompletion
    ) -> None:
        with self.session_factory() as db:
            db.add(
                ModelCallTrace(
                    id=str(uuid4()),
                    run_id=state["run_id"],
                    owner_id=state["owner_id"],
                    sequence=sequence,
                    status="succeeded",
                    provider=completion.provider,
                    model=completion.model,
                    latency_ms=completion.latency_ms,
                    prompt_tokens=completion.usage.prompt_tokens,
                    completion_tokens=completion.usage.completion_tokens,
                    total_tokens=completion.usage.total_tokens,
                    selected_tools_json="[]",
                    created_at=datetime.now(UTC),
                )
            )
            db.commit()

    def _record_model_error(
        self,
        state: MultiAgentState,
        sequence: int,
        error: ModelProviderError,
        started: float,
    ) -> None:
        with self.session_factory() as db:
            db.add(
                ModelCallTrace(
                    id=str(uuid4()),
                    run_id=state["run_id"],
                    owner_id=state["owner_id"],
                    sequence=sequence,
                    status="failed",
                    provider=self.provider.provider,
                    model=self.provider.model,
                    latency_ms=max(0, round((monotonic() - started) * 1000)),
                    error_code=error.code,
                    created_at=datetime.now(UTC),
                )
            )
            db.commit()

    def _record_model_invalid(
        self,
        state: MultiAgentState,
        sequence: int,
        completion: ModelCompletion,
    ) -> None:
        with self.session_factory() as db:
            db.add(
                ModelCallTrace(
                    id=str(uuid4()),
                    run_id=state["run_id"],
                    owner_id=state["owner_id"],
                    sequence=sequence,
                    status="failed",
                    provider=completion.provider,
                    model=completion.model,
                    latency_ms=completion.latency_ms,
                    prompt_tokens=completion.usage.prompt_tokens,
                    completion_tokens=completion.usage.completion_tokens,
                    total_tokens=completion.usage.total_tokens,
                    selected_tools_json="[]",
                    error_code="INVALID_SUPERVISOR_HANDOFF",
                    created_at=datetime.now(UTC),
                )
            )
            db.commit()

    def _record_step(
        self,
        state: MultiAgentState,
        sequence: int,
        node: str,
        status: str,
        input_summary: dict[str, Any],
        output_summary: dict[str, Any],
        started: float,
        error_code: str | None,
    ) -> None:
        with self.session_factory() as db:
            db.add(
                AgentStepTrace(
                    id=str(uuid4()),
                    run_id=state["run_id"],
                    owner_id=state["owner_id"],
                    sequence=sequence,
                    node=node,
                    status=status,
                    input_summary_json=json.dumps(
                        input_summary, ensure_ascii=False, separators=(",", ":")
                    ),
                    output_summary_json=json.dumps(
                        output_summary, ensure_ascii=False, separators=(",", ":")
                    ),
                    duration_ms=max(0, round((monotonic() - started) * 1000)),
                    error_code=error_code,
                    created_at=datetime.now(UTC),
                )
            )
            db.commit()
