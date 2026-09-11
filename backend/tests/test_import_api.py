from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.imports import owner_context
from app.db.session import get_db
from app.main import app
from app.models.base import Base


def _xlsx_content() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["微信支付账单明细"])
    worksheet.append(["统计时间", "2026-01-01 至 2026-01-31"])
    worksheet.append([])
    worksheet.append(
        [
            "交易时间",
            "交易类型",
            "交易对方",
            "商品",
            "收/支",
            "金额(元)",
            "支付方式",
            "交易状态",
            "交易单号",
        ]
    )
    worksheet.append(
        [
            datetime(2026, 1, 3, 8, 12, 30),
            "商户消费",
            "早餐店",
            "早餐",
            "支出",
            12.5,
            "零钱",
            "支付成功",
            "WX-API-XLSX-001",
        ]
    )
    content = BytesIO()
    workbook.save(content)
    return content.getvalue()


def test_import_and_transaction_api_contract(sample_dir, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[owner_context] = lambda: "api-owner"
    try:
        client = TestClient(app, backend_options={"use_uvloop": True})
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
        transfers = client.get("/api/v1/transactions?direction=transfer")
        assert transfers.status_code == 200
        assert transfers.json()["total"] == 1
        transaction_id = transactions.json()["items"][0]["id"]

        changed = client.patch(
            f"/api/v1/transactions/{transaction_id}/category",
            json={"category": "餐饮"},
        )
        assert changed.status_code == 200
        assert changed.json()["transaction"]["category"] == "餐饮"
    finally:
        app.dependency_overrides.clear()


def test_xlsx_upload_infers_format(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'xlsx-api.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[owner_context] = lambda: "xlsx-api-owner"
    try:
        response = TestClient(app, backend_options={"use_uvloop": True}).post(
            "/api/v1/imports",
            files={
                "file": (
                    "wechat-export.xlsx",
                    _xlsx_content(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["format"] == "xlsx"
        assert body["status"] == "completed"
        assert body["total_rows"] == 1
        assert body["success_rows"] == 1
    finally:
        app.dependency_overrides.clear()
