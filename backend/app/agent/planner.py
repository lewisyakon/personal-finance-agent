"""Validated dynamic task graphs with bounded parallel execution and replanning."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.contracts import AgentExecutionResult
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
from app.models.agent import AgentRun, ModelCallTrace
from app.models.multi_agent import AgentStepTrace
from app.models.planning import AgentPlanTrace
from app.schemas.planning import (
    PlanTask,
    PlanValidationIssue,
    PlanValidationResult,
    TaskGraph,
)
from app.services.budget_service import BudgetService
from app.services.memory_service import MemoryService
from app.tools.contracts import OwnerContext, ToolExecutionResult
from app.tools.registry import ToolRegistry, readonly_tool_registry
from app.tools.runtime import ToolExecutor

SessionFactory = Callable[[], Session]

_PLANNER_PROMPT = """你是个人消费分析 Planner，只输出符合 Schema 的任务图。
任务只能使用给定 Agent 和只读 Tool。depends_on 表示显式依赖；无依赖任务可并行。
Tool 参数必须是严格 Schema 参数，不得包含 owner_id、SQL、路径、URL 或写操作。
涉及预算时由 budget Agent 使用确定性统计 Tool；预算草案之后仍需用户确认。
不要输出思考过程或自然语言报告。
"""

_AGENT_TOOL_PERMISSIONS: dict[str, frozenset[str]] = {
    "analysis": frozenset(item.name for item in readonly_tool_registry.definitions()),
    "transaction": frozenset(
        {
            "get_spending_summary",
            "get_category_breakdown",
            "get_trend",
            "get_top_merchants",
            "get_large_transactions",
            "search_transactions",
            "compare_periods",
        }
    ),
    "semantic": frozenset({"get_merchant_history"}),
    "budget": frozenset({"get_spending_summary", "get_category_breakdown", "get_budget_status"}),
}


class PlanValidator:
    def __init__(self, registry: ToolRegistry = readonly_tool_registry) -> None:
        self.registry = registry

    def validate(self, graph: TaskGraph) -> PlanValidationResult:
        issues: list[PlanValidationIssue] = []
        task_ids = {task.task_id for task in graph.tasks}
        for task in graph.tasks:
            allowed = _AGENT_TOOL_PERMISSIONS.get(task.agent)
            if allowed is None:
                issues.append(
                    PlanValidationIssue(
                        code="UNKNOWN_AGENT",
                        task_id=task.task_id,
                        message="计划包含未知 Agent",
                    )
                )
            definition = self.registry.get(task.tool_name)
            if definition is None:
                issues.append(
                    PlanValidationIssue(
                        code="UNKNOWN_TOOL",
                        task_id=task.task_id,
                        message="计划包含未知 Tool",
                    )
                )
            elif allowed is not None and task.tool_name not in allowed:
                issues.append(
                    PlanValidationIssue(
                        code="TOOL_NOT_ALLOWED",
                        task_id=task.task_id,
                        message="Agent 无权使用该 Tool",
                    )
                )
            else:
                try:
                    definition.arguments_model.model_validate(task.arguments)
                except ValidationError:
                    issues.append(
                        PlanValidationIssue(
                            code="INVALID_TOOL_ARGUMENTS",
                            task_id=task.task_id,
                            message="Tool 参数未通过严格 Schema 校验",
                        )
                    )
            for dependency in task.depends_on:
                if dependency == task.task_id:
                    issues.append(
                        PlanValidationIssue(
                            code="SELF_DEPENDENCY",
                            task_id=task.task_id,
                            message="任务不能依赖自身",
                        )
                    )
                elif dependency not in task_ids:
                    issues.append(
                        PlanValidationIssue(
                            code="UNKNOWN_DEPENDENCY",
                            task_id=task.task_id,
                            message="任务依赖不存在",
                        )
                    )
        waves = self._execution_waves(graph) if not issues else []
        if not issues and not waves:
            issues.append(
                PlanValidationIssue(
                    code="CYCLIC_DEPENDENCY",
                    message="计划包含循环依赖",
                )
            )
        return PlanValidationResult(valid=not issues, issues=issues, execution_waves=waves)

    @staticmethod
    def _execution_waves(graph: TaskGraph) -> list[list[str]]:
        remaining = {task.task_id: set(task.depends_on) for task in graph.tasks}
        waves: list[list[str]] = []
        completed: set[str] = set()
        while remaining:
            wave = sorted(
                task_id
                for task_id, dependencies in remaining.items()
                if dependencies.issubset(completed)
            )
            if not wave:
                return []
            waves.append(wave)
            completed.update(wave)
            for task_id in wave:
                remaining.pop(task_id)
        return waves


def detect_task_disagreement(results: list[ToolExecutionResult]) -> bool:
    periods: set[tuple[str, str]] = set()
    currencies: set[str] = set()
    for result in results:
        data = result.data or {}
        period = data.get("period")
        if isinstance(period, dict) and period.get("start") and period.get("end"):
            periods.add((str(period["start"]), str(period["end"])))
        currency = data.get("currency")
        if currency:
            currencies.add(str(currency))
    return len(periods) > 1 or len(currencies) > 1


class PlanExecutor:
    def __init__(
        self,
        tool_executor: ToolExecutor,
        validator: PlanValidator,
        *,
        max_workers: int = 4,
    ) -> None:
        self.tool_executor = tool_executor
        self.validator = validator
        self.max_workers = max_workers

    def execute(
        self,
        graph: TaskGraph,
        context: OwnerContext,
        run_id: str,
        token: CancellationToken,
        *,
        remaining_tool_calls: int,
    ) -> tuple[list[tuple[PlanTask, ToolExecutionResult, int]], PlanValidationResult]:
        validation = self.validator.validate(graph)
        if not validation.valid:
            return [], validation
        if len(graph.tasks) > remaining_tool_calls:
            return [], PlanValidationResult(
                valid=False,
                issues=[
                    PlanValidationIssue(
                        code="TOOL_NOT_ALLOWED",
                        message="计划超过本次运行剩余 Tool 调用上限",
                    )
                ],
            )
        tasks = {task.task_id: task for task in graph.tasks}
        completed: dict[str, ToolExecutionResult] = {}
        output: list[tuple[PlanTask, ToolExecutionResult, int]] = []
        for wave_index, wave in enumerate(validation.execution_waves):
            token.raise_if_cancelled()
            runnable = [tasks[task_id] for task_id in wave]
            with ThreadPoolExecutor(
                max_workers=min(self.max_workers, len(runnable)),
                thread_name_prefix="pfa-plan",
            ) as pool:
                futures = {
                    task.task_id: pool.submit(
                        self.tool_executor.execute,
                        task.tool_name,
                        task.arguments,
                        context,
                        run_id=run_id,
                    )
                    for task in runnable
                }
                for task in runnable:
                    result = futures[task.task_id].result()
                    completed[task.task_id] = result
                    output.append((task, result, wave_index))
            if any(completed[task_id].status != "success" for task_id in wave):
                break
        return output, validation


class PlannerAgent:
    def __init__(
        self,
        provider: ModelProvider,
        tool_executor: ToolExecutor,
        session_factory: SessionFactory,
        budget_service: BudgetService,
        *,
        registry: ToolRegistry = readonly_tool_registry,
        settings: Settings | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.provider = provider
        self.tool_executor = tool_executor
        self.session_factory = session_factory
        self.budget_service = budget_service
        self.registry = registry
        self.settings = settings or get_settings()
        self.memory_service = memory_service
        self.validator = PlanValidator(registry)
        self.executor = PlanExecutor(
            tool_executor,
            self.validator,
            max_workers=self.settings.planner_parallel_workers,
        )

    def run(
        self,
        run_id: str,
        user_query: str,
        context: OwnerContext,
        cancellation_token: CancellationToken | None = None,
    ) -> AgentExecutionResult:
        token = cancellation_token or CancellationToken()
        started = monotonic()
        all_results: list[tuple[PlanTask, ToolExecutionResult, int]] = []
        prompt_tokens = completion_tokens = total_tokens = 0
        model_calls = step_count = replans = 0
        memory_context: list[dict[str, Any]] = []
        if self.memory_service is not None:
            with self.session_factory() as db:
                stored_run = db.get(AgentRun, run_id)
                session_id = stored_run.session_id if stored_run is not None else None
            retrieved = self.memory_service.retrieve(
                context.owner_id,
                user_query,
                run_id=run_id,
                session_id=session_id,
            )
            for item in retrieved.items[:20]:
                candidate = {
                    "scope": item.scope,
                    "kind": item.kind,
                    "key": item.key,
                    "value": item.value,
                    "source": item.source,
                }
                prospective = [*memory_context, candidate]
                if len(json.dumps(prospective, ensure_ascii=False)) > (
                    self.settings.agent_max_context_chars // 2
                ):
                    break
                memory_context.append(candidate)
        try:
            graph, completion = self._request_plan(
                run_id,
                user_query,
                token,
                version=1,
                memory_context=memory_context,
            )
            model_calls += 1
            step_count += 1
            prompt_tokens += completion.usage.prompt_tokens
            completion_tokens += completion.usage.completion_tokens
            total_tokens += completion.usage.total_tokens
            self._record_model(run_id, context.owner_id, model_calls, completion)
            validation = self.validator.validate(graph)
            self._record_plan(run_id, context.owner_id, graph, validation)
            self._record_step(
                run_id,
                context.owner_id,
                1,
                "planner",
                "succeeded" if validation.valid else "failed",
                {"task_count": len(graph.tasks), "version": graph.version},
                {"wave_count": len(validation.execution_waves)},
                None if validation.valid else "INVALID_PLAN",
                started,
            )
            if not validation.valid:
                return self._failure(
                    run_id,
                    "INVALID_PLAN",
                    "Planner 生成的任务图未通过校验",
                    step_count,
                    model_calls,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    started,
                )
            self._check_limits(
                started,
                step_count,
                model_calls,
                total_tokens,
                prompt_tokens,
                completion_tokens,
            )
            results, execution_validation = self.executor.execute(
                graph,
                context,
                run_id,
                token,
                remaining_tool_calls=self.settings.agent_max_tool_calls,
            )
            if not execution_validation.valid:
                return self._failure(
                    run_id,
                    "AGENT_TOOL_LIMIT",
                    "计划超过 Tool 调用上限",
                    step_count,
                    model_calls,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    started,
                )
            all_results.extend(results)
            for task, result, wave in results:
                step_count += 1
                self._record_step(
                    run_id,
                    context.owner_id,
                    step_count,
                    task.agent,
                    result.status,
                    {
                        "task_id": task.task_id,
                        "wave": wave,
                        "dependency_count": len(task.depends_on),
                    },
                    {"tool": task.tool_name, "has_evidence": result.status == "success"},
                    result.error.code if result.error else None,
                    started,
                )
            if any(result.status != "success" for _, result, _ in results):
                return self._failure(
                    run_id,
                    "PLAN_TASK_FAILED",
                    "计划中的只读 Tool 未成功完成",
                    step_count,
                    model_calls,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    started,
                    all_results,
                )

            if graph.allow_replan and results and replans < self.settings.agent_max_replans:
                self._check_limits(
                    started,
                    step_count,
                    model_calls,
                    total_tokens,
                    prompt_tokens,
                    completion_tokens,
                )
                graph, completion = self._request_plan(
                    run_id,
                    user_query,
                    token,
                    version=2,
                    evidence=[
                        {
                            "task_id": task.task_id,
                            "tool": task.tool_name,
                            "status": result.status,
                            "evidence_id": result.evidence_id,
                        }
                        for task, result, _ in results
                    ],
                    memory_context=memory_context,
                )
                replans += 1
                model_calls += 1
                step_count += 1
                prompt_tokens += completion.usage.prompt_tokens
                completion_tokens += completion.usage.completion_tokens
                total_tokens += completion.usage.total_tokens
                self._record_model(run_id, context.owner_id, model_calls, completion)
                validation = self.validator.validate(graph)
                self._record_plan(
                    run_id,
                    context.owner_id,
                    graph,
                    validation,
                    replan_reason="new_evidence",
                )
                self._record_step(
                    run_id,
                    context.owner_id,
                    step_count,
                    "planner",
                    "succeeded" if validation.valid else "failed",
                    {
                        "task_count": len(graph.tasks),
                        "version": graph.version,
                        "replanned": True,
                    },
                    {"wave_count": len(validation.execution_waves)},
                    None if validation.valid else "INVALID_REPLAN",
                    started,
                )
                if not validation.valid:
                    return self._failure(
                        run_id,
                        "INVALID_REPLAN",
                        "新证据触发的计划未通过校验",
                        step_count,
                        model_calls,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        started,
                        all_results,
                    )
                new_results, execution_validation = self.executor.execute(
                    graph,
                    context,
                    run_id,
                    token,
                    remaining_tool_calls=self.settings.agent_max_tool_calls - len(all_results),
                )
                if not execution_validation.valid:
                    return self._failure(
                        run_id,
                        "AGENT_TOOL_LIMIT",
                        "重新规划超过 Tool 调用上限",
                        step_count,
                        model_calls,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        started,
                        all_results,
                    )
                all_results.extend(new_results)
                for task, result, wave in new_results:
                    step_count += 1
                    self._record_step(
                        run_id,
                        context.owner_id,
                        step_count,
                        task.agent,
                        result.status,
                        {"task_id": task.task_id, "wave": wave, "replanned": True},
                        {"tool": task.tool_name, "has_evidence": result.status == "success"},
                        result.error.code if result.error else None,
                        started,
                    )
            self._check_limits(
                started,
                step_count,
                model_calls,
                total_tokens,
                prompt_tokens,
                completion_tokens,
            )
        except ModelProviderError as exc:
            return self._failure(
                run_id,
                exc.code,
                exc.message,
                step_count,
                model_calls,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                started,
                all_results,
                status="cancelled" if exc.code == "MODEL_CANCELLED" else "failed",
            )
        except (ValidationError, ValueError):
            return self._failure(
                run_id,
                "PLANNER_PROTOCOL_ERROR",
                "Planner 响应结构无效",
                step_count,
                model_calls,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                started,
                all_results,
            )

        successful = [result for _, result, _ in all_results if result.status == "success"]
        evidence_refs = [result.evidence_id for result in successful]
        tool_names = [task.tool_name for task, _, _ in all_results]
        tool_results = [result.model_dump(mode="json") for result in successful]
        if detect_task_disagreement(successful):
            self.budget_service.create_disagreement_confirmation(
                context.owner_id,
                run_id,
                "多个 Tool 返回的周期或币种不一致，需要用户选择后继续",
            )
            return AgentExecutionResult(
                run_id=run_id,
                status="needs_confirmation",
                answer="检测到证据分歧，需要用户确认后继续。",
                error_code="EVIDENCE_DISAGREEMENT",
                error_message="证据周期或币种不一致",
                evidence_refs=evidence_refs,
                tool_names=tool_names,
                tool_results=tool_results,
                step_count=step_count,
                tool_call_count=len(all_results),
                model_call_count=model_calls,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_microusd=self._estimated_cost(prompt_tokens, completion_tokens),
                duration_ms=max(0, round((monotonic() - started) * 1000)),
            )

        budget_tasks = [
            (task, result)
            for task, result, _ in all_results
            if task.agent == "budget" and task.tool_name == "get_spending_summary"
        ]
        if budget_tasks:
            if step_count + 1 > self.settings.agent_max_steps:
                return self._failure(
                    run_id,
                    "AGENT_STEP_LIMIT",
                    "Planner 步数超过限制",
                    step_count,
                    model_calls,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    started,
                    all_results,
                )
            budget, _confirmation = self.budget_service.propose_from_evidence(
                context.owner_id,
                budget_tasks[0][1],
                1000,
                run_id=run_id,
            )
            step_count += 1
            self._record_step(
                run_id,
                context.owner_id,
                step_count,
                "budget_confirmation",
                "needs_confirmation",
                {"evidence_id": budget_tasks[0][1].evidence_id},
                {"budget_id": budget.id, "status": budget.status},
                None,
                started,
            )
            return AgentExecutionResult(
                run_id=run_id,
                status="needs_confirmation",
                answer=(
                    f"预算草案为{Decimal(budget.proposed_budget_minor) / Decimal(100):.2f}元，"
                    "确认后才会保存为长期偏好。"
                ),
                evidence_refs=evidence_refs,
                tool_names=tool_names,
                tool_results=tool_results,
                step_count=step_count,
                tool_call_count=len(all_results),
                model_call_count=model_calls,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_microusd=self._estimated_cost(prompt_tokens, completion_tokens),
                duration_ms=max(0, round((monotonic() - started) * 1000)),
            )
        return AgentExecutionResult(
            run_id=run_id,
            status="succeeded",
            answer=f"规划任务已完成，共获得{len(evidence_refs)}条可重放证据。",
            evidence_refs=evidence_refs,
            tool_names=tool_names,
            tool_results=tool_results,
            step_count=step_count,
            tool_call_count=len(all_results),
            model_call_count=model_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_microusd=self._estimated_cost(prompt_tokens, completion_tokens),
            duration_ms=max(0, round((monotonic() - started) * 1000)),
        )

    def _request_plan(
        self,
        run_id: str,
        user_query: str,
        token: CancellationToken,
        *,
        version: int,
        evidence: list[dict[str, Any]] | None = None,
        memory_context: list[dict[str, Any]] | None = None,
    ) -> tuple[TaskGraph, ModelCompletion]:
        content = user_query
        response_name = "planner_task_graph"
        if evidence is not None:
            response_name = "planner_replan"
            content = json.dumps(
                {"query": user_query, "new_evidence": evidence},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        messages = [
            ModelMessage(role="developer", content=_PLANNER_PROMPT),
            ModelMessage(
                role="developer",
                content=json.dumps(
                    {
                        "agents": {
                            key: sorted(value) for key, value in _AGENT_TOOL_PERMISSIONS.items()
                        }
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
            ModelMessage(
                role="developer",
                content=json.dumps(
                    {"user_confirmed_memory": memory_context or []},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
            ModelMessage(role="user", content=content),
        ]
        if sum(len(message.content or "") for message in messages) > (
            self.settings.agent_max_context_chars
        ):
            raise ModelProviderError("AGENT_CONTEXT_LIMIT", "Planner 模型上下文超过限制")
        completion = self.provider.complete(
            ModelRequest(
                run_id=run_id,
                messages=messages,
                response_format=StructuredOutputSpec(
                    name=response_name,
                    schema=TaskGraph.model_json_schema(),
                ),
            ),
            token,
        )
        graph = TaskGraph.model_validate_json(completion.content or "")
        if graph.version != version:
            graph = graph.model_copy(update={"version": version})
        return graph, completion

    def _check_limits(
        self,
        started: float,
        step_count: int,
        model_calls: int,
        total_tokens: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        if monotonic() - started >= self.settings.agent_total_timeout_seconds:
            raise ModelProviderError("AGENT_TIMEOUT", "Planner 总运行时间超过限制")
        if step_count > self.settings.agent_max_steps:
            raise ModelProviderError("AGENT_STEP_LIMIT", "Planner 步数超过限制")
        if model_calls > self.settings.agent_max_model_calls:
            raise ModelProviderError("AGENT_MODEL_LIMIT", "Planner 模型调用次数超过限制")
        if total_tokens > self.settings.agent_max_total_tokens:
            raise ModelProviderError("AGENT_TOKEN_LIMIT", "Planner Token 使用超过限制")
        if (
            self._estimated_cost(prompt_tokens, completion_tokens)
            > self.settings.agent_max_cost_microusd
        ):
            raise ModelProviderError("AGENT_COST_LIMIT", "Planner 估算模型费用超过限制")

    def _estimated_cost(self, prompt_tokens: int, completion_tokens: int) -> int:
        numerator = (
            prompt_tokens * self.settings.llm_input_cost_per_million_microusd
            + completion_tokens * self.settings.llm_output_cost_per_million_microusd
        )
        return (numerator + 999_999) // 1_000_000

    def _record_plan(
        self,
        run_id: str,
        owner_id: str,
        graph: TaskGraph,
        validation: PlanValidationResult,
        *,
        replan_reason: str | None = None,
    ) -> None:
        with self.session_factory() as db:
            db.add(
                AgentPlanTrace(
                    id=str(uuid4()),
                    run_id=run_id,
                    owner_id=owner_id,
                    version=graph.version,
                    status="valid" if validation.valid else "invalid",
                    plan_json=graph.model_dump_json(),
                    validation_errors_json=json.dumps(
                        [item.model_dump(mode="json") for item in validation.issues],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    replan_reason=replan_reason,
                    created_at=datetime.now(UTC),
                )
            )
            db.commit()

    def _record_model(
        self,
        run_id: str,
        owner_id: str,
        sequence: int,
        completion: ModelCompletion,
    ) -> None:
        with self.session_factory() as db:
            db.add(
                ModelCallTrace(
                    id=str(uuid4()),
                    run_id=run_id,
                    owner_id=owner_id,
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

    def _record_step(
        self,
        run_id: str,
        owner_id: str,
        sequence: int,
        node: str,
        status: str,
        input_summary: dict[str, Any],
        output_summary: dict[str, Any],
        error_code: str | None,
        started: float,
    ) -> None:
        with self.session_factory() as db:
            db.add(
                AgentStepTrace(
                    id=str(uuid4()),
                    run_id=run_id,
                    owner_id=owner_id,
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

    def _failure(
        self,
        run_id: str,
        code: str,
        message: str,
        step_count: int,
        model_calls: int,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        started: float,
        results: list[tuple[PlanTask, ToolExecutionResult, int]] | None = None,
        *,
        status: str = "failed",
    ) -> AgentExecutionResult:
        collected = results or []
        successful = [result for _, result, _ in collected if result.status == "success"]
        return AgentExecutionResult(
            run_id=run_id,
            status=status,
            answer=f"无法确定：{message}。",
            error_code=code,
            error_message=message,
            evidence_refs=[result.evidence_id for result in successful],
            tool_names=[task.tool_name for task, _, _ in collected],
            tool_results=[result.model_dump(mode="json") for result in successful],
            step_count=step_count,
            tool_call_count=len(collected),
            model_call_count=model_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_microusd=self._estimated_cost(prompt_tokens, completion_tokens),
            duration_ms=max(0, round((monotonic() - started) * 1000)),
        )
