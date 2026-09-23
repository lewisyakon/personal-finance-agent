import json
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.llm.contracts import ModelCompletion, TokenUsage
from app.llm.provider import MockModelProvider
from app.models.base import Base
from app.models.finance import BillImport, Transaction, WorkspaceOwner
from app.models.semantic import MerchantRule
from app.services.memory_service import MemoryService
from app.services.semantic_service import SemanticClassificationService, normalize_merchant
from app.tools.runtime import ToolExecutor

TZ = ZoneInfo("Asia/Shanghai")


class CountingMockProvider(MockModelProvider):
    def __init__(self, script=None):
        super().__init__("semantic-test", script)
        self.call_count = 0

    def complete(self, request, cancellation_token=None):
        self.call_count += 1
        return super().complete(request, cancellation_token)


def _decision(category: str, confidence: float) -> ModelCompletion:
    return ModelCompletion(
        provider="mock",
        model="semantic-test",
        content=json.dumps(
            {
                "category": category,
                "confidence": confidence,
                "rationale": "合成语义分类测试",
            },
            ensure_ascii=False,
        ),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="semantic-test",
        SEMANTIC_AUTO_APPLY_THRESHOLD=0.85,
    )


def _seed(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'semantic.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(WorkspaceOwner(id="owner-a", display_name="Semantic 测试用户"))
        db.add(
            BillImport(
                id="semantic-import",
                owner_id="owner-a",
                file_name="synthetic.csv",
                file_sha256="d" * 64,
                status="completed",
            )
        )

        def add(row: int, merchant: str, platform_category: str, category=None, source=None):
            item = Transaction(
                owner_id="owner-a",
                bill_import_id="semantic-import",
                fingerprint=f"semantic-{row}",
                occurred_at=datetime(2026, 1, row, 12, tzinfo=TZ),
                direction="expense",
                amount_minor=100 * row,
                currency="CNY",
                status="success",
                merchant=merchant,
                description=f"{merchant} 商品",
                platform_category=platform_category,
                category=category,
                category_source=source,
                source_row=row,
            )
            db.add(item)
            db.flush()
            return item.id

        ids = {
            "unknown_1": add(1, "微信支付-星河咖啡", "其他"),
            "unknown_2": add(2, "星河咖啡", "其他"),
            "platform": add(3, "城市地铁", "交通/地铁"),
            "history": add(4, "历史商店", "其他"),
            "history_source": add(5, "历史商店", "购物/日用", "购物/日用", "user"),
            "corrected": add(6, "人工商户", "其他", "医疗", "user"),
            "high": add(7, "高置信商户", "其他"),
        }
        db.commit()
    return factory, ids


def test_rule_first_semantic_flow_low_confidence_confirmation_and_reuse(tmp_path):
    factory, ids = _seed(tmp_path)
    provider = CountingMockProvider([_decision("餐饮", 0.4)])
    memories = MemoryService(factory)
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = SemanticClassificationService(
            factory,
            provider,
            executor,
            settings=_settings(),
            memory_service=memories,
        )
        pending = service.classify("owner-a", ids["unknown_1"])
        repeated_pending = service.classify("owner-a", ids["unknown_1"])
        confirmed = service.confirm("owner-a", pending.id, "餐饮/咖啡", save_rule=True)
        reused = service.classify("owner-a", ids["unknown_2"])

    assert pending.status == "pending"
    assert pending.model_called is True
    assert pending.confidence == 0.4
    assert pending.evidence_refs[0].startswith("ev_")
    assert repeated_pending.id == pending.id
    assert confirmed.status == "confirmed"
    assert reused.route == "user_rule"
    assert reused.suggested_category == "餐饮/咖啡"
    assert reused.model_called is False
    assert provider.call_count == 1

    with factory() as db:
        transaction = db.get(Transaction, ids["unknown_2"])
        rule = db.scalar(
            select(MerchantRule).where(
                MerchantRule.normalized_merchant == normalize_merchant("星河咖啡")
            )
        )
    assert transaction is not None and transaction.category == "餐饮/咖啡"
    assert rule is not None and rule.category == "餐饮/咖啡"
    stored_memories = memories.list("owner-a", "long_term")
    assert stored_memories.total == 1
    assert stored_memories.items[0].kind == "merchant_rule"
    assert stored_memories.items[0].source == "user_confirmed"
    assert service.delete_rule("owner-a", rule.id) is True
    assert memories.list("owner-a", "long_term").total == 0


def test_platform_history_and_user_correction_bypass_model(tmp_path):
    factory, ids = _seed(tmp_path)
    provider = CountingMockProvider()
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = SemanticClassificationService(factory, provider, executor, settings=_settings())
        platform = service.classify("owner-a", ids["platform"])
        history = service.classify("owner-a", ids["history"])
        corrected = service.classify("owner-a", ids["corrected"])

    assert platform.route == "platform"
    assert platform.suggested_category == "交通/地铁"
    assert history.route == "history"
    assert history.suggested_category == "购物/日用"
    assert history.evidence_refs
    assert corrected.route == "user_rule"
    assert corrected.suggested_category == "医疗"
    assert provider.call_count == 0
    with factory() as db:
        corrected_transaction = db.get(Transaction, ids["corrected"])
    assert corrected_transaction is not None
    assert corrected_transaction.category_source == "user"


def test_high_confidence_model_classification_is_applied_but_not_saved_as_rule(tmp_path):
    factory, ids = _seed(tmp_path)
    provider = CountingMockProvider([_decision("购物", 0.91)])
    memories = MemoryService(factory)
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = SemanticClassificationService(
            factory,
            provider,
            executor,
            settings=_settings(),
            memory_service=memories,
        )
        result = service.classify("owner-a", ids["high"])

    assert result.status == "applied"
    assert result.route == "model"
    with factory() as db:
        transaction = db.get(Transaction, ids["high"])
        rules = list(db.scalars(select(MerchantRule)))
    assert transaction is not None and transaction.category == "购物"
    assert transaction.category_source == "semantic_model"
    assert rules == []
    assert memories.list("owner-a").total == 0


def test_semantic_http_api_supports_pending_confirmation_and_rule_management(tmp_path):
    from fastapi.testclient import TestClient

    from app.api.imports import owner_context
    from app.api.semantic import semantic_service
    from app.main import app

    factory, ids = _seed(tmp_path)
    provider = CountingMockProvider([_decision("餐饮", 0.4)])
    with ToolExecutor(factory, timeout_seconds=2) as executor:
        service = SemanticClassificationService(factory, provider, executor, settings=_settings())
        app.dependency_overrides[owner_context] = lambda: "owner-a"
        app.dependency_overrides[semantic_service] = lambda: service
        try:
            with TestClient(app) as client:
                classified = client.post(
                    f"/api/v1/semantic/transactions/{ids['unknown_1']}/classify"
                )
                assert classified.status_code == 200
                suggestion = classified.json()
                assert suggestion["status"] == "pending"

                pending = client.get("/api/v1/semantic/suggestions?status=pending")
                assert pending.status_code == 200
                assert pending.json()["total"] == 1

                confirmed = client.post(
                    f"/api/v1/semantic/suggestions/{suggestion['id']}/confirm",
                    json={"category": "餐饮/咖啡", "save_rule": True},
                )
                assert confirmed.status_code == 200
                assert confirmed.json()["status"] == "confirmed"

                rules = client.get("/api/v1/semantic/rules")
                assert rules.status_code == 200
                rule_id = rules.json()["items"][0]["id"]
                assert rules.json()["items"][0]["category"] == "餐饮/咖啡"
                assert client.delete(f"/api/v1/semantic/rules/{rule_id}").status_code == 204
        finally:
            app.dependency_overrides.clear()
