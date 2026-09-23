import threading
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agent.planner import PlanExecutor, PlanValidator
from app.agent.service import AgentService
from app.core.config import Settings
from app.llm.contracts import CancellationToken
from app.llm.provider import MockModelProvider
from app.models.base import Base
from app.models.finance import BillImport, Transaction, WorkspaceOwner
from app.models.planning import AgentPlanTrace, BudgetPlan
from app.schemas.planning import PlanTask, TaskGraph
from app.services.budget_service import BudgetService
from app.tools.contracts import OwnerContext, ToolExecutionResult, ToolMethodology
from app.tools.runtime import ToolExecutor

TZ = ZoneInfo("Asia/Shanghai")


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="planner-test",
        AGENT_MAX_STEPS=12,
        AGENT_MAX_TOOL_CALLS=8,
        AGENT_MAX_MODEL_CALLS=4,
        AGENT_TOTAL_TIMEOUT_SECONDS=10,
        AGENT_MAX_TOTAL_TOKENS=1000,
        AGENT_MAX_REPLANS=1,
        PLANNER_PARALLEL_WORKERS=4,
    )


def _seed(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'planner.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(WorkspaceOwner(id="owner-a", display_name="Planner 测试用户"))
        db.add(
            BillImport(
                id="planner-import",
                owner_id="owner-a",
                file_name="synthetic.csv",
                file_sha256="f" * 64,
                status="completed",
            )
        )
        db.add_all(
            [
                Transaction(
                    owner_id="owner-a",
                    bill_import_id="planner-import",
                    fingerprint="planner-1",
                    occurred_at=datetime(2026, 1, 3, 12, tzinfo=TZ),
                    direction="expense",
                    amount_minor=10_000,
                    currency="CNY",
                    status="success",
                    merchant="房租",
                    platform_category="住房",
                    source_row=1,
                ),
                Transaction(
                    owner_id="owner-a",
                    bill_import_id="planner-import",
                    fingerprint="planner-2",
                    occurred_at=datetime(2026, 1, 8, 12, tzinfo=TZ),
                    direction="expense",
                    amount_minor=5_000,
                    currency="CNY",
                    status="success",
                    merchant="餐厅",
                    platform_category="餐饮",
                    source_row=2,
                ),
            ]
        )
        db.commit()
    return factory


def _task(task_id, tool="get_spending_summary", *, depends_on=None, agent="analysis"):
    return PlanTask(
        task_id=task_id,
        agent=agent,
        objective="合成计划测试",
        tool_name=tool,
        arguments={
            "from": "2026-01-01T00:00:00+08:00",
            "to": "2026-02-01T00:00:00+08:00",
        },
        depends_on=depends_on or [],
    )


def test_plan_validator_rejects_unknowns_permissions_arguments_and_cycles():
    validator = PlanValidator()
    invalid = TaskGraph(
        tasks=[
            _task("unknown-agent", agent="mystery"),
            _task("forbidden", tool="get_merchant_history", agent="budget"),
            PlanTask(
                task_id="bad-args",
                agent="analysis",
                objective="非法参数",
                tool_name="get_spending_summary",
                arguments={"owner_id": "other"},
            ),
            _task("cycle-a", depends_on=["cycle-b"]),
            _task("cycle-b", depends_on=["cycle-a"]),
        ]
    )
    result = validator.validate(invalid)
    codes = {issue.code for issue in result.issues}
    assert result.valid is False
    assert {"UNKNOWN_AGENT", "TOOL_NOT_ALLOWED", "INVALID_TOOL_ARGUMENTS"} <= codes

    cyclic = validator.validate(
        TaskGraph(tasks=[_task("a", depends_on=["b"]), _task("b", depends_on=["a"])])
    )
    assert [issue.code for issue in cyclic.issues] == ["CYCLIC_DEPENDENCY"]


def test_plan_executor_runs_independent_tasks_in_parallel_then_dependencies():
    events: dict[str, float] = {}
    lock = threading.Lock()

    class FakeExecutor:
        def execute(self, tool_name, arguments, context, *, run_id=None):
            with lock:
                events[f"{tool_name}:start"] = time.monotonic()
            time.sleep(0.05)
            with lock:
                events[f"{tool_name}:end"] = time.monotonic()
            now = datetime.now(UTC)
            return ToolExecutionResult(
                evidence_id=f"ev_{tool_name}",
                tool_name=tool_name,
                status="success",
                data={"period": {"start": arguments["from"], "end": arguments["to"]}},
                methodology=ToolMethodology(
                    source_service="stats_service",
                    period_semantics="[from, to)",
                    timezone="Asia/Shanghai",
                ),
                started_at=now,
                completed_at=now,
                duration_ms=50,
            )

    graph = TaskGraph(
        tasks=[
            _task("summary", "get_spending_summary"),
            PlanTask(
                task_id="categories",
                agent="analysis",
                objective="合成计划测试",
                tool_name="get_category_breakdown",
                arguments={
                    "from": "2026-01-01T00:00:00+08:00",
                    "to": "2026-02-01T00:00:00+08:00",
                    "direction": "expense",
                },
                depends_on=[],
            ),
            PlanTask(
                task_id="merchants",
                agent="analysis",
                objective="合成计划测试",
                tool_name="get_top_merchants",
                arguments={
                    "from": "2026-01-01T00:00:00+08:00",
                    "to": "2026-02-01T00:00:00+08:00",
                    "direction": "expense",
                    "limit": 10,
                },
                depends_on=["summary", "categories"],
            ),
        ]
    )
    executor = PlanExecutor(FakeExecutor(), PlanValidator(), max_workers=2)
    results, validation = executor.execute(
        graph,
        OwnerContext(owner_id="owner-a"),
        "run-a",
        cancellation_token := CancellationToken(),
        remaining_tool_calls=8,
    )
    assert cancellation_token.cancelled is False
    assert validation.execution_waves == [["categories", "summary"], ["merchants"]]
    assert len(results) == 3
    assert events["get_category_breakdown:start"] < events["get_spending_summary:end"]
    assert events["get_top_merchants:start"] >= max(
        events["get_spending_summary:end"], events["get_category_breakdown:end"]
    )


def test_budget_numbers_come_from_tool_and_require_confirmation(tmp_path):
    factory = _seed(tmp_path)
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = BudgetService(factory, executor)
        budget, confirmation = service.propose(
            "owner-a",
            datetime(2026, 1, 1, tzinfo=TZ),
            datetime(2026, 2, 1, tzinfo=TZ),
            1000,
        )
        assert budget.baseline_expense_minor == 15_000
        assert budget.proposed_budget_minor == 13_500
        assert budget.status == "draft"
        assert budget.evidence_refs[0].startswith("ev_")
        resolved = service.resolve_confirmation("owner-a", confirmation.id, "confirm")
        confirmed = service.get("owner-a", budget.id)

    assert resolved.status == "confirmed"
    assert confirmed is not None and confirmed.status == "confirmed"


def test_planner_workflow_replans_once_and_budget_auto_routing_waits_for_user(tmp_path):
    from app.agent.planner import PlannerAgent

    factory = _seed(tmp_path)
    provider = MockModelProvider("planner-test")
    settings = _settings()
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        budgets = BudgetService(factory, executor)
        service = AgentService(
            factory,
            provider,
            executor,
            settings=settings,
            planner_agent_factory=lambda: PlannerAgent(
                provider,
                executor,
                factory,
                budgets,
                settings=settings,
            ),
        )
        replanned = service.chat("owner-a", "重新规划并综合分析2026年1月支出", workflow="planner")
        budget = service.chat("owner-a", "为2026年1月制定预算")

    assert replanned.status == "succeeded"
    assert replanned.workflow == "planner"
    assert replanned.metrics.model_call_count == 2
    assert replanned.metrics.tool_call_count == 4
    assert replanned.metrics.step_count == len(replanned.agent_steps)
    assert [step.node for step in replanned.agent_steps].count("planner") == 2
    assert budget.workflow == "planner"
    assert budget.status == "needs_confirmation"
    assert budget.metrics.step_count == len(budget.agent_steps)
    assert budget.agent_steps[-1].node == "budget_confirmation"
    with factory() as db:
        plans = list(
            db.scalars(
                select(AgentPlanTrace)
                .where(AgentPlanTrace.run_id == replanned.id)
                .order_by(AgentPlanTrace.version)
            )
        )
        draft = db.scalar(select(BudgetPlan).where(BudgetPlan.run_id == budget.id))
    assert [plan.version for plan in plans] == [1, 2]
    assert plans[1].replan_reason == "new_evidence"
    assert draft is not None and draft.status == "draft"


def test_planner_stops_safely_at_tool_and_cost_limits(tmp_path):
    from app.agent.planner import PlannerAgent

    factory = _seed(tmp_path)
    provider = MockModelProvider("planner-test")
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        budgets = BudgetService(factory, executor)
        tool_limited_settings = _settings().model_copy(update={"agent_max_tool_calls": 1})
        tool_limited = AgentService(
            factory,
            provider,
            executor,
            settings=tool_limited_settings,
            planner_agent_factory=lambda: PlannerAgent(
                provider,
                executor,
                factory,
                budgets,
                settings=tool_limited_settings,
            ),
        ).chat("owner-a", "为2026年1月制定预算", workflow="planner")

        cost_settings = _settings().model_copy(
            update={
                "llm_input_cost_per_million_microusd": 1_000_000,
                "llm_output_cost_per_million_microusd": 1_000_000,
                "agent_max_cost_microusd": 0,
            }
        )
        cost_limited = AgentService(
            factory,
            provider,
            executor,
            settings=cost_settings,
            planner_agent_factory=lambda: PlannerAgent(
                provider,
                executor,
                factory,
                budgets,
                settings=cost_settings,
            ),
        ).chat("owner-a", "综合分析2026年1月支出", workflow="planner")

    assert tool_limited.status == "failed"
    assert tool_limited.error_code == "AGENT_TOOL_LIMIT"
    assert tool_limited.metrics.tool_call_count == 0
    assert cost_limited.status == "failed"
    assert cost_limited.error_code == "AGENT_COST_LIMIT"
    assert cost_limited.metrics.estimated_cost_microusd == 2


def test_budget_http_api_requires_explicit_confirmation(tmp_path):
    from fastapi.testclient import TestClient

    from app.api.imports import owner_context
    from app.api.planning import budget_service
    from app.main import app

    factory = _seed(tmp_path)
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = BudgetService(factory, executor)
        app.dependency_overrides[owner_context] = lambda: "owner-a"
        app.dependency_overrides[budget_service] = lambda: service
        try:
            with TestClient(app) as client:
                created = client.post(
                    "/api/v1/budgets/drafts",
                    json={
                        "from": "2026-01-01T00:00:00+08:00",
                        "to": "2026-02-01T00:00:00+08:00",
                        "reduction_percent": 20,
                    },
                )
                assert created.status_code == 200
                assert created.json()["proposed_budget_minor"] == 12_000
                assert created.json()["status"] == "draft"

                confirmations = client.get("/api/v1/agent/confirmations")
                confirmation_id = confirmations.json()["items"][0]["id"]
                resolved = client.post(
                    f"/api/v1/agent/confirmations/{confirmation_id}/resolve",
                    json={"decision": "confirm"},
                )
                assert resolved.status_code == 200
                assert resolved.json()["status"] == "confirmed"

                listed = client.get("/api/v1/budgets")
                assert listed.json()["items"][0]["status"] == "confirmed"
        finally:
            app.dependency_overrides.clear()
