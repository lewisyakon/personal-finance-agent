from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agent.multi_agent import MultiAgent
from app.agent.service import AgentService
from app.core.config import Settings, get_settings
from app.evals.runner import load_dataset, run_architecture_comparison
from app.llm.provider import MockModelProvider
from app.models.agent import AgentEvaluationRun
from app.models.base import Base
from app.services.import_service import InProcessImportExecutor, create_import
from app.tools.runtime import ToolExecutor

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "datasets"
    / "sanitized_samples"
    / "stage3_stats_fixture.csv"
)


def test_stage5_and_stage7_have_30_case_repeatable_mock_baseline(tmp_path, monkeypatch):
    dataset = load_dataset()
    assert len(dataset.cases) == 30
    assert len({case.id for case in dataset.cases}) == 30

    global_settings = get_settings()
    monkeypatch.setattr(global_settings, "data_dir", tmp_path / "data")
    global_settings.ensure_data_dirs()
    engine = create_engine(
        f"sqlite:///{tmp_path / 'evaluation.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        item, reused = create_import(
            db,
            "evaluation-owner",
            FIXTURE.name,
            FIXTURE.read_bytes(),
        )
        assert reused is False
        imported = InProcessImportExecutor(db).execute(item.id, "evaluation-owner")
        assert imported.status == "completed"

    settings = Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="stage5-baseline",
        AGENT_MAX_STEPS=8,
        AGENT_MAX_TOOL_CALLS=3,
        AGENT_MAX_MODEL_CALLS=4,
        AGENT_TOTAL_TIMEOUT_SECONDS=10,
        AGENT_MAX_TOTAL_TOKENS=1000,
    )
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        provider = MockModelProvider("stage5-baseline")
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
            unverified_multi_agent_factory=lambda: MultiAgent(
                provider,
                executor,
                factory,
                settings=settings,
                verification_enabled=False,
            ),
        )
        comparison = run_architecture_comparison(service, "evaluation-owner", dataset)

    report = comparison.single

    assert report.status == "passed"
    assert report.case_count == 30
    assert report.pass_rate >= dataset.minimum_pass_rate
    assert report.tool_selection_accuracy == 1
    assert report.numeric_accuracy == 1
    assert report.total_tokens > 0
    assert report.workflow == "single"
    assert comparison.multi_unverified.status == "passed"
    assert comparison.multi_unverified.workflow == "multi_unverified"
    assert comparison.multi_verified.status == "passed"
    assert comparison.multi_verified.workflow == "multi"
    for item in (comparison.multi_unverified, comparison.multi_verified):
        assert item.pass_rate == report.pass_rate
        assert item.tool_selection_accuracy == report.tool_selection_accuracy
        assert item.numeric_accuracy == report.numeric_accuracy
        assert item.task_completion_rate == 1
        assert item.evidence_coverage == 1
        assert item.hallucination_rate == 0
        assert item.p95_latency_ms >= item.p50_latency_ms
    assert comparison.multi_verified.total_tokens > report.total_tokens
    assert report.average_handoff_count == 0
    assert comparison.multi_unverified.average_handoff_count == 2
    assert comparison.multi_verified.average_handoff_count == 2
    with factory() as db:
        stored = list(db.scalars(select(AgentEvaluationRun).order_by(AgentEvaluationRun.workflow)))
    assert [(item.workflow, item.case_count, item.status) for item in stored] == [
        ("multi", 30, "passed"),
        ("multi_unverified", 30, "passed"),
        ("single", 30, "passed"),
    ]
