from fastapi.testclient import TestClient

from app.main import app


def test_system_status_is_local_and_structured():
    response = TestClient(app, backend_options={"use_uvloop": True}).get(
        "/api/v1/system/status"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["app"]["available"] is True
    assert body["database"]["available"] is True
    assert body["model"]["available"] is True
