from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.imports import owner_context
from app.db.session import get_db
from app.main import app
from app.models.base import Base


def test_import_and_transaction_api_contract(sample_dir, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", future=True)
    Base.metadata.create_all(engine)

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[owner_context] = lambda: "api-owner"
    try:
        client = TestClient(app)
        content = (Path(sample_dir) / "wechat_sample_utf8.csv").read_bytes()
        response = client.post(
            "/api/v1/imports",
            files={"file": ("sample.csv", content, "text/csv")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "completed"
        assert body["success_rows"] == 3

        repeated = client.post(
            "/api/v1/imports",
            files={"file": ("renamed.csv", content, "text/csv")},
        )
        assert repeated.status_code == 201
        assert repeated.json()["idempotent_reuse"] is True

        transactions = client.get("/api/v1/transactions?direction=expense&page_size=2")
        assert transactions.status_code == 200
        assert transactions.json()["total"] == 2
        transaction_id = transactions.json()["items"][0]["id"]

        changed = client.patch(
            f"/api/v1/transactions/{transaction_id}/category",
            json={"category": "餐饮"},
        )
        assert changed.status_code == 200
        assert changed.json()["transaction"]["category"] == "餐饮"
    finally:
        app.dependency_overrides.clear()
