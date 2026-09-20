from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.agent.service import AgentService
from app.core.config import Settings
from app.llm.contracts import (
    ModelCompletion,
    ModelHealth,
    ModelProviderError,
    ModelToolCall,
    TokenUsage,
)
from app.llm.provider import MockModelProvider
from app.models.agent import AgentRun, AgentSession, ModelCallTrace
from app.models.base import Base
from app.models.finance import BillImport, Transaction, WorkspaceOwner
from app.models.tooling import ToolTrace
from app.tools.runtime import ToolExecutor

TZ = ZoneInfo("Asia/Shanghai")
PERIOD = {
    "from": "2026-01-01T00:00:00+08:00",
    "to": "2026-02-01T00:00:00+08:00",
}


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="test-model",
        AGENT_MAX_STEPS=8,
        AGENT_MAX_TOOL_CALLS=3,
        AGENT_MAX_MODEL_CALLS=4,
        AGENT_TOTAL_TIMEOUT_SECONDS=10,
        AGENT_MAX_TOTAL_TOKENS=1000,
    )


def _seed_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'agent.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(WorkspaceOwner(id="owner-a", display_name="Agent 测试用户"))
        db.add(
            BillImport(
                id="agent-import",
                owner_id="owner-a",
                file_name="fixture.csv",
                file_sha256="a" * 64,
                status="completed",
            )
        )
        db.add_all(
            [
                Transaction(
                    owner_id="owner-a",
                    bill_import_id="agent-import",
                    fingerprint="agent-expense",
                    occurred_at=datetime(2026, 1, 3, 12, tzinfo=TZ),
                    direction="expense",
                    amount_minor=6700,
                    currency="CNY",
                    status="success",
                    merchant="测试商户",
                    category="餐饮",
                    source_row=1,
                ),
                Transaction(
                    owner_id="owner-a",
                    bill_import_id="agent-import",
                    fingerprint="agent-income",
                    occurred_at=datetime(2026, 1, 5, 12, tzinfo=TZ),
                    direction="income",
                    amount_minor=10000,
                    currency="CNY",
                    status="success",
                    merchant="测试公司",
                    category="工资",
                    source_row=2,
                ),
            ]
        )
        db.commit()
    return engine, factory


def _script(answer: str) -> list[ModelCompletion]:
    return [
        ModelCompletion(
            provider="mock",
            model="test-model",
            tool_calls=[
                ModelToolCall(
                    id="call_summary",
                    name="get_spending_summary",
                    arguments=PERIOD,
                )
            ],
            usage=TokenUsage(prompt_tokens=8, completion_tokens=2, total_tokens=10),
        ),
        ModelCompletion(
            provider="mock",
            model="test-model",
            content=answer,
            usage=TokenUsage(prompt_tokens=12, completion_tokens=4, total_tokens=16),
        ),
    ]


def test_single_agent_uses_tool_grounding_and_persists_minimal_traces(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    provider = MockModelProvider("test-model", _script("本期支出为67.00元。"))

    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = AgentService(factory, provider, executor, settings=_settings())
        result = service.chat("owner-a", "2026年1月支出是多少？")

    assert result.status == "succeeded"
    assert "67.00元" in result.answer
    assert result.evidence_refs[0].startswith("ev_")
    assert result.tool_names == ["get_spending_summary"]
    assert result.metrics.model_call_count == 2
    assert result.metrics.tool_call_count == 1
    assert result.metrics.total_tokens == 26

    with factory() as db:
        run = db.get(AgentRun, result.id)
        tool_trace = db.scalar(select(ToolTrace).where(ToolTrace.run_id == result.id))
        model_traces = list(
            db.scalars(
                select(ModelCallTrace)
                .where(ModelCallTrace.run_id == result.id)
                .order_by(ModelCallTrace.sequence)
            )
        )
        assert db.scalar(select(func.count()).select_from(AgentSession)) == 1

    assert run is not None and run.status == "succeeded"
    assert tool_trace is not None and tool_trace.owner_id == "owner-a"
    assert [trace.selected_tools_json for trace in model_traces] == [
        '["get_spending_summary"]',
        "[]",
    ]
    assert not hasattr(model_traces[0], "prompt")
    assert not hasattr(model_traces[0], "reasoning")


def test_single_agent_rejects_ungrounded_money_claim(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    provider = MockModelProvider("test-model", _script("本期支出为999.00元。"))

    with ToolExecutor(factory, timeout_seconds=2) as executor:
        result = AgentService(
            factory,
            provider,
            executor,
            settings=_settings(),
        ).chat("owner-a", "2026年1月支出是多少？")

    assert result.status == "failed"
    assert result.error_code == "UNGROUNDED_NUMERIC_CLAIM"
    assert "999.00元" not in (result.answer or "")
    assert result.evidence_refs


class UnavailableProvider:
    provider = "local"
    model = "unavailable-model"

    def health(self) -> ModelHealth:
        return ModelHealth(
            provider=self.provider,
            model=self.model,
            available=False,
            message="model service unavailable",
        )

    def complete(self, _request, _cancellation_token=None):
        raise ModelProviderError("MODEL_UNAVAILABLE", "模型服务不可用", retryable=True)


def test_single_agent_surfaces_provider_failure_without_fallback(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        result = AgentService(
            factory,
            UnavailableProvider(),
            executor,
            settings=_settings(),
        ).chat("owner-a", "2026年1月支出是多少？")

    assert result.status == "failed"
    assert result.provider == "local"
    assert result.model == "unavailable-model"
    assert result.error_code == "MODEL_UNAVAILABLE"
    assert result.metrics.model_call_count == 1
    assert result.metrics.tool_call_count == 0
    assert result.evidence_refs == []


def test_single_agent_rejects_parallel_tool_calls(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    parallel = ModelCompletion(
        provider="mock",
        model="test-model",
        tool_calls=[
            ModelToolCall(id="call_1", name="get_spending_summary", arguments=PERIOD),
            ModelToolCall(id="call_2", name="get_spending_summary", arguments=PERIOD),
        ],
    )
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        result = AgentService(
            factory,
            MockModelProvider("test-model", [parallel]),
            executor,
            settings=_settings(),
        ).chat("owner-a", "2026年1月支出是多少？")

    assert result.status == "failed"
    assert result.error_code == "AGENT_PROTOCOL_ERROR"
    assert result.metrics.model_call_count == 1
    assert result.metrics.tool_call_count == 0


def test_mock_provider_supports_model_free_basic_agent_run(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        result = AgentService(
            factory,
            MockModelProvider("mock-finance"),
            executor,
            settings=_settings(),
        ).chat("owner-a", "请查2026年1月的收支汇总")

    assert result.status == "succeeded"
    assert result.tool_names == ["get_spending_summary"]
    assert "67.00元" in (result.answer or "")


def test_session_and_run_reads_are_owner_scoped(tmp_path):
    _engine, factory = _seed_database(tmp_path)
    provider = MockModelProvider("test-model", _script("本期支出为67.00元。"))
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = AgentService(factory, provider, executor, settings=_settings())
        result = service.chat("owner-a", "查支出")
        session = service.get_session("owner-a", result.session_id)
        sessions = service.list_sessions("owner-a", 1, 20)
        missing_session = service.get_session("owner-b", result.session_id)
        missing_run = service.get_run("owner-b", result.id)

    assert session is not None and session.run_count == 1
    assert sessions.total == 1
    assert missing_session is None
    assert missing_run is None


def test_agent_http_api_exposes_chat_sessions_runs_and_cancel(tmp_path):
    from fastapi.testclient import TestClient

    from app.api.agent import agent_service
    from app.api.imports import owner_context
    from app.main import app

    _engine, factory = _seed_database(tmp_path)
    provider = MockModelProvider("test-model", _script("本期支出为67.00元。"))
    executor = ToolExecutor(factory, timeout_seconds=2)
    service = AgentService(factory, provider, executor, settings=_settings())
    app.dependency_overrides[agent_service] = lambda: service
    app.dependency_overrides[owner_context] = lambda: "owner-a"
    try:
        with TestClient(app, backend_options={"use_uvloop": True}) as client:
            chat = client.post(
                "/api/v1/agent/chat",
                json={"message": "2026年1月支出是多少？"},
            )
            assert chat.status_code == 200
            payload = chat.json()
            run_id = payload["id"]
            session_id = payload["session_id"]

            sessions = client.get("/api/v1/agent/sessions")
            session = client.get(f"/api/v1/agent/sessions/{session_id}")
            run = client.get(f"/api/v1/agent/runs/{run_id}")
            cancelled_terminal = client.post(f"/api/v1/agent/runs/{run_id}/cancel")
            missing = client.get("/api/v1/agent/runs/missing")

        assert sessions.status_code == 200 and sessions.json()["total"] == 1
        assert session.status_code == 200 and session.json()["run_count"] == 1
        assert run.status_code == 200 and run.json()["status"] == "succeeded"
        assert cancelled_terminal.json()["status"] == "succeeded"
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "AGENT_RUN_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
        executor.close()
