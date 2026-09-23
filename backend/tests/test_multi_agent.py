from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.handoffs import AnalysisHandoff, AnalysisTask, SupervisorHandoff
from app.agent.multi_agent import MultiAgent
from app.agent.registry import fixed_agent_registry
from app.agent.service import AgentService
from app.agent.verifier import verify_analysis
from app.core.config import Settings
from app.llm.contracts import ModelCompletion, TokenUsage
from app.llm.provider import MockModelProvider
from app.models.base import Base
from app.models.finance import BillImport, Transaction, WorkspaceOwner
from app.tools.runtime import ToolExecutor

TZ = ZoneInfo("Asia/Shanghai")


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="multi-test",
        AGENT_MAX_STEPS=8,
        AGENT_MAX_TOOL_CALLS=3,
        AGENT_MAX_MODEL_CALLS=5,
        AGENT_TOTAL_TIMEOUT_SECONDS=10,
        AGENT_MAX_TOTAL_TOKENS=1000,
    )


def _seed(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'multi.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(WorkspaceOwner(id="owner-a", display_name="Multi-Agent 测试用户"))
        db.add(
            BillImport(
                id="multi-import",
                owner_id="owner-a",
                file_name="synthetic.csv",
                file_sha256="e" * 64,
                status="completed",
            )
        )
        for row, occurred, amount, direction, merchant in (
            (1, datetime(2025, 12, 10, 12, tzinfo=TZ), 3000, "expense", "上月商户"),
            (2, datetime(2026, 1, 3, 12, tzinfo=TZ), 6700, "expense", "本月商户"),
            (3, datetime(2026, 1, 8, 12, tzinfo=TZ), 10000, "income", "公司"),
        ):
            db.add(
                Transaction(
                    owner_id="owner-a",
                    bill_import_id="multi-import",
                    fingerprint=f"multi-{row}",
                    occurred_at=occurred,
                    direction=direction,
                    amount_minor=amount,
                    currency="CNY",
                    status="success",
                    merchant=merchant,
                    platform_category="其他",
                    source_row=row,
                )
            )
        db.commit()
    return factory


def _service(factory, executor):
    provider = MockModelProvider("multi-test")
    settings = _settings()
    return AgentService(
        factory,
        provider,
        executor,
        settings=settings,
        multi_agent_factory=lambda: MultiAgent(
            provider,
            executor,
            factory,
            settings=settings,
        ),
    )


def test_auto_routing_keeps_simple_fast_path_and_uses_fixed_graph_for_complex(tmp_path):
    factory = _seed(tmp_path)
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = _service(factory, executor)
        simple = service.chat("owner-a", "2026年1月支出是多少？")
        complex_run = service.chat("owner-a", "分析2026年1月每天的支出趋势")

    assert simple.status == "succeeded"
    assert simple.workflow == "single"
    assert simple.agent_steps == []
    assert simple.metrics.model_call_count == 2

    assert complex_run.status == "succeeded"
    assert complex_run.workflow == "multi"
    assert complex_run.tool_names == ["get_trend"]
    assert [step.node for step in complex_run.agent_steps] == [
        "supervisor",
        "analysis",
        "verifier",
    ]
    assert complex_run.metrics.step_count == 5
    assert complex_run.metrics.model_call_count == 3
    assert all("分析2026" not in str(step.input_summary) for step in complex_run.agent_steps)


def test_verifier_detects_amount_time_direction_tool_and_evidence_errors():
    supervisor = SupervisorHandoff(
        normalized_intent="核对一月支出",
        date_from="2026-01-01T00:00:00+08:00",
        date_to="2026-02-01T00:00:00+08:00",
        direction="expense",
        plan=[
            AnalysisTask(
                task_id="analysis-1",
                agent="analysis",
                objective="查询支出",
                required_tools=["get_spending_summary"],
            )
        ],
    )
    analysis = AnalysisHandoff(
        status="succeeded",
        answer="本期支出为999.00元。",
        evidence_refs=[],
        tool_names=["get_trend"],
        tool_results=[
            {
                "status": "success",
                "data": {
                    "period": {
                        "start": "2026-02-01T00:00:00+08:00",
                        "end": "2026-03-01T00:00:00+08:00",
                    },
                    "direction": "income",
                    "amount_minor": 100,
                },
            }
        ],
        error_code=None,
        error_message=None,
    )

    result = verify_analysis(supervisor, analysis)
    codes = {item.code for item in result.issues}
    assert result.passed is False
    assert codes == {
        "MISSING_EVIDENCE",
        "UNGROUNDED_AMOUNT",
        "TIME_RANGE_MISMATCH",
        "DIRECTION_MISMATCH",
        "MISSING_PLANNED_TOOL",
    }


def test_registry_prevents_cross_namespace_updates():
    fixed_agent_registry.validate_update(
        "supervisor", {"normalized_intent": "summary", "plan": [], "constraints": {}}
    )
    with pytest.raises(ValueError, match="越权"):
        fixed_agent_registry.validate_update("analysis", {"verification": {"passed": True}})


def test_single_and_multi_results_can_be_compared_on_same_query(tmp_path):
    factory = _seed(tmp_path)
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        comparison = _service(factory, executor).compare("owner-a", "对比2026年1月与前一周期的支出")

    assert comparison.single.workflow == "single"
    assert comparison.multi.workflow == "multi"
    assert comparison.single.status == comparison.multi.status == "succeeded"
    assert comparison.same_tools is True
    assert comparison.shared_evidence_count == 1
    assert comparison.multi.agent_steps[-1].output_summary["passed"] is True
    assert comparison.token_delta > 0


def test_invalid_supervisor_handoff_terminates_after_fixed_nodes(tmp_path):
    factory = _seed(tmp_path)
    provider = MockModelProvider(
        "multi-test",
        [
            ModelCompletion(
                provider="mock",
                model="multi-test",
                content="{}",
                usage=TokenUsage(prompt_tokens=2, completion_tokens=1, total_tokens=3),
            )
        ],
    )
    settings = _settings()
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = AgentService(
            factory,
            provider,
            executor,
            settings=settings,
            multi_agent_factory=lambda: MultiAgent(
                provider,
                executor,
                factory,
                settings=settings,
            ),
        )
        result = service.chat("owner-a", "分析2026年1月支出", workflow="multi")

    assert result.status == "failed"
    assert result.error_code == "VERIFICATION_FAILED"
    assert [step.node for step in result.agent_steps] == [
        "supervisor",
        "analysis",
        "verifier",
    ]
    assert result.metrics.model_call_count == 1
    assert len(result.model_calls) == 1
    assert result.model_calls[0].error_code == "INVALID_SUPERVISOR_HANDOFF"


def test_multi_agent_http_api_exposes_workflow_and_comparison(tmp_path):
    from fastapi.testclient import TestClient

    from app.api.agent import agent_service
    from app.api.imports import owner_context
    from app.main import app

    factory = _seed(tmp_path)
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = _service(factory, executor)
        app.dependency_overrides[owner_context] = lambda: "owner-a"
        app.dependency_overrides[agent_service] = lambda: service
        try:
            with TestClient(app) as client:
                chat = client.post(
                    "/api/v1/agent/chat",
                    json={
                        "message": "分析2026年1月每天的支出趋势",
                        "workflow": "multi",
                    },
                )
                assert chat.status_code == 200
                assert chat.json()["workflow"] == "multi"
                assert [step["node"] for step in chat.json()["agent_steps"]] == [
                    "supervisor",
                    "analysis",
                    "verifier",
                ]

                comparison = client.post(
                    "/api/v1/agent/compare",
                    json={"message": "对比2026年1月与前一周期的支出"},
                )
                assert comparison.status_code == 200
                body = comparison.json()
                assert body["single"]["workflow"] == "single"
                assert body["multi"]["workflow"] == "multi"
                assert body["same_tools"] is True
        finally:
            app.dependency_overrides.clear()
