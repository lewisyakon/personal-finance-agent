from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.planner import PlannerAgent
from app.agent.service import AgentService
from app.core.config import Settings
from app.llm.provider import MockModelProvider
from app.models.base import Base
from app.models.finance import BillImport, Transaction, WorkspaceOwner
from app.models.memory import MemoryRecord
from app.models.semantic import MerchantRule
from app.services.budget_service import BudgetService
from app.services.memory_service import MemoryService
from app.tools.runtime import ToolExecutor


def _seed(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'memory.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(WorkspaceOwner(id="owner-a", display_name="Memory 测试用户"))
        db.add(
            BillImport(
                id="memory-import",
                owner_id="owner-a",
                file_name="synthetic.csv",
                file_sha256="b" * 64,
                status="completed",
            )
        )
        db.add(
            Transaction(
                owner_id="owner-a",
                bill_import_id="memory-import",
                fingerprint="memory-1",
                occurred_at=datetime(2026, 1, 3, 12, tzinfo=UTC),
                direction="expense",
                amount_minor=10_000,
                currency="CNY",
                status="success",
                merchant="星河咖啡",
                platform_category="其他",
                source_row=1,
            )
        )
        db.commit()
    return factory


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="memory-test",
        AGENT_MAX_STEPS=12,
        AGENT_MAX_TOOL_CALLS=8,
        AGENT_MAX_MODEL_CALLS=4,
        AGENT_TOTAL_TIMEOUT_SECONDS=10,
        AGENT_MAX_TOTAL_TOKENS=1000,
    )


def test_memory_conflict_expiry_delete_and_retrieval_trace(tmp_path):
    factory = _seed(tmp_path)
    service = MemoryService(factory)
    with factory() as db:
        rule = MerchantRule(
            id="rule-a",
            owner_id="owner-a",
            normalized_merchant="星河咖啡",
            display_merchant="星河咖啡",
            category="餐饮",
            source="user_confirmed",
            active=True,
        )
        db.add(rule)
        db.commit()

    first = service.remember(
        "owner-a",
        "long_term",
        "merchant_rule",
        "星河咖啡",
        {"category": "餐饮"},
        source_ref_type="merchant_rule",
        source_ref_id="rule-a",
    )
    hit = service.retrieve("owner-a", "星河咖啡应该属于什么类别？")
    second = service.remember(
        "owner-a",
        "long_term",
        "merchant_rule",
        "星河咖啡",
        {"category": "餐饮/咖啡"},
        source_ref_type="merchant_rule",
        source_ref_id="rule-a",
    )
    session_memory = service.remember(
        "owner-a",
        "session",
        "conversation_preference",
        "回答风格",
        {"session_id": "session-a", "style": "concise"},
    )
    wrong_session = service.retrieve(
        "owner-a",
        "回答风格",
        session_id="session-b",
    )
    matching_session = service.retrieve(
        "owner-a",
        "回答风格",
        session_id="session-a",
    )

    assert hit.status == "hit"
    assert hit.items[0].source == "user_confirmed"
    assert second.version == 2 and second.supersedes_id == first.id
    assert session_memory.expires_at is not None
    assert wrong_session.status == "miss"
    assert matching_session.status == "hit"
    with factory() as db:
        expired = db.get(MemoryRecord, session_memory.id)
        assert expired is not None
        expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert service.list("owner-a", "session").total == 0

    assert service.delete("owner-a", second.id) is True
    miss = service.retrieve("owner-a", "星河咖啡应该属于什么类别？")
    accesses = service.list_accesses("owner-a")
    assert miss.status == "miss"
    assert accesses.items[0].status == "miss"
    assert any(item.status == "hit" for item in accesses.items)
    with factory() as db:
        stored_rule = db.get(MerchantRule, "rule-a")
        old = db.get(MemoryRecord, first.id)
    assert stored_rule is not None and stored_rule.active is False
    assert old is not None and old.status == "superseded"


def test_confirmed_budget_becomes_memory_and_planner_explains_hit(tmp_path):
    factory = _seed(tmp_path)
    memories = MemoryService(factory)
    provider = MockModelProvider("memory-test")
    settings = _settings()
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        budgets = BudgetService(factory, executor, memories)
        draft, confirmation = budgets.propose(
            "owner-a",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 2, 1, tzinfo=UTC),
            1000,
        )
        assert memories.list("owner-a").total == 0
        budgets.resolve_confirmation("owner-a", confirmation.id, "confirm")
        stored = memories.list("owner-a", "long_term")
        assert stored.total == 1
        assert stored.items[0].kind == "budget_preference"
        assert stored.items[0].value["budget_minor"] == draft.proposed_budget_minor
        updated_budget = budgets.update("owner-a", draft.id, 12_345)
        updated_memory = memories.list("owner-a", "long_term")
        assert updated_budget.proposed_budget_minor == 12_345
        assert updated_memory.items[0].version == 2
        assert updated_memory.items[0].value["budget_minor"] == 12_345

        agent = AgentService(
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
                memory_service=memories,
            ),
        )
        run = agent.chat("owner-a", "为2026年1月重新制定预算", workflow="planner")

    accesses = memories.list_accesses("owner-a")
    assert run.status == "needs_confirmation"
    assert accesses.items[0].run_id == run.id
    assert accesses.items[0].status == "hit"
    assert accesses.items[0].reason == "matched_active_user_confirmed_memory"


def test_memory_http_api_create_update_delete(tmp_path):
    from fastapi.testclient import TestClient

    from app.api.imports import owner_context
    from app.api.memory import memory_service
    from app.main import app

    factory = _seed(tmp_path)
    service = MemoryService(factory)
    app.dependency_overrides[owner_context] = lambda: "owner-a"
    app.dependency_overrides[memory_service] = lambda: service
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/memories",
                json={
                    "scope": "knowledge",
                    "kind": "preference",
                    "key": "报告语言",
                    "value": {"language": "zh-CN"},
                },
            )
            assert created.status_code == 201
            assert created.json()["source"] == "user_confirmed"
            memory_id = created.json()["id"]

            updated = client.patch(
                f"/api/v1/memories/{memory_id}",
                json={"value": {"language": "zh-Hans"}},
            )
            assert updated.status_code == 200
            assert updated.json()["version"] == 2
            assert updated.json()["supersedes_id"] == memory_id

            listed = client.get("/api/v1/memories?scope=knowledge")
            active_id = listed.json()["items"][0]["id"]
            assert listed.json()["total"] == 1
            assert client.delete(f"/api/v1/memories/{active_id}").status_code == 204
            assert client.get("/api/v1/memories").json()["total"] == 0
    finally:
        app.dependency_overrides.clear()
