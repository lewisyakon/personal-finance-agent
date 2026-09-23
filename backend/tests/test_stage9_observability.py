from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.multi_agent import MultiAgent
from app.agent.service import AgentService
from app.api.developer import developer_guard
from app.core.config import Settings
from app.llm.provider import MockModelProvider
from app.models.agent import AgentEvaluationRun, EvaluationFailureSample
from app.models.base import Base
from app.models.finance import BillImport, Transaction, WorkspaceOwner
from app.services.developer_service import DeveloperService
from app.tools.runtime import ToolExecutor


def _seed(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'developer.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(WorkspaceOwner(id="owner-a", display_name="Developer 测试用户"))
        db.add(
            BillImport(
                id="developer-import",
                owner_id="owner-a",
                file_name="synthetic.csv",
                file_sha256="a" * 64,
                status="completed",
            )
        )
        db.add(
            Transaction(
                owner_id="owner-a",
                bill_import_id="developer-import",
                fingerprint="developer-1",
                occurred_at=datetime(2026, 1, 3, 12, tzinfo=UTC),
                direction="expense",
                amount_minor=1_000,
                currency="CNY",
                status="success",
                merchant="合成商户",
                platform_category="餐饮",
                source_row=1,
            )
        )
        db.commit()
    return factory


def _settings(**updates) -> Settings:
    values = {
        "_env_file": None,
        "LLM_PROVIDER": "mock",
        "LLM_MODEL": "developer-test",
        "AGENT_MAX_STEPS": 8,
        "AGENT_MAX_TOOL_CALLS": 3,
        "AGENT_MAX_MODEL_CALLS": 5,
        "AGENT_TOTAL_TIMEOUT_SECONDS": 10,
        "AGENT_MAX_TOTAL_TOKENS": 1000,
    }
    values.update(updates)
    return Settings(**values)


def test_developer_service_locates_node_model_tool_and_evaluation_failures(tmp_path):
    factory = _seed(tmp_path)
    provider = MockModelProvider("developer-test")
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
        run = service.chat("owner-a", "分析2026年1月支出", workflow="multi")

    now = datetime.now(UTC)
    evaluation_id = "eval-stage9"
    with factory() as db:
        db.add(
            AgentEvaluationRun(
                id=evaluation_id,
                owner_id="owner-a",
                comparison_group_id="comparison-stage9",
                dataset_version="stage9-test-v1",
                provider="mock",
                model="developer-test",
                workflow="multi",
                status="failed",
                case_count=1,
                passed_count=0,
                tool_selection_accuracy_bp=10_000,
                numeric_accuracy_bp=0,
                task_completion_bp=0,
                evidence_coverage_bp=10_000,
                hallucination_rate_bp=0,
                routing_accuracy_bp=10_000,
                average_handoff_count_bp=300,
                average_latency_ms=12,
                p50_latency_ms=12,
                p95_latency_ms=12,
                total_tokens=6,
                estimated_cost_microusd=0,
                results_json="[]",
                started_at=now,
                completed_at=now,
            )
        )
        db.add(
            EvaluationFailureSample(
                id="failure-stage9",
                evaluation_run_id=evaluation_id,
                owner_id="owner-a",
                dataset_version="stage9-test-v1",
                case_id="case-1",
                workflow="multi",
                error_stage="verification",
                error_code="VERIFICATION_FAILED",
                summary_json='{"status":"failed"}',
                created_at=now,
            )
        )
        db.commit()

    developer = DeveloperService(factory)
    listed = developer.list_runs("owner-a", 1, 20)
    detail = developer.run_detail("owner-a", run.id)
    evaluations = developer.list_evaluations("owner-a")
    comparisons = developer.list_comparisons("owner-a")
    failures = developer.list_failures("owner-a")

    assert listed.total == 1
    assert detail is not None
    assert [step.node for step in detail.run.agent_steps] == [
        "supervisor",
        "analysis",
        "verifier",
    ]
    assert detail.tool_traces[0].evidence_id.startswith("ev_")
    assert detail.run.model_calls
    assert evaluations.items[0].numeric_accuracy == 0
    assert comparisons.items[0].comparison_group_id == "comparison-stage9"
    assert failures.items[0].error_stage == "verification"
    assert "arguments" not in detail.tool_traces[0].model_dump()

    from fastapi.testclient import TestClient

    from app.api.developer import developer_service
    from app.api.imports import owner_context
    from app.main import app

    app.dependency_overrides[owner_context] = lambda: "owner-a"
    app.dependency_overrides[developer_service] = lambda: developer
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/developer/runs/{run.id}")
            assert response.status_code == 200
            assert response.json()["run"]["workflow"] == "multi"
            assert response.json()["tool_traces"][0]["tool_name"] == "get_spending_summary"
    finally:
        app.dependency_overrides.clear()


def test_developer_endpoints_are_hidden_outside_local_development():
    with pytest.raises(HTTPException) as exc_info:
        developer_guard(_settings(APP_MODE="production", DEVELOPER_ENABLED=True))
    assert exc_info.value.status_code == 404

    developer_guard(_settings(APP_MODE="local", DEVELOPER_ENABLED=True))
