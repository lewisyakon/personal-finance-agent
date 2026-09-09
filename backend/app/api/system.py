from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.session import check_database
from app.llm.provider import MockModelProvider

router = APIRouter(prefix="/system", tags=["system"])


class ComponentStatus(BaseModel):
    available: bool
    message: str


class SystemStatus(BaseModel):
    app: ComponentStatus
    database: ComponentStatus
    model: ComponentStatus


@router.get("/status", response_model=SystemStatus)
def status() -> SystemStatus:
    settings = get_settings()
    model = MockModelProvider(settings.llm_model).health()
    database_ok = check_database()
    return SystemStatus(
        app=ComponentStatus(available=True, message=f"mode={settings.app_mode}"),
        database=ComponentStatus(
            available=database_ok,
            message="sqlite ready" if database_ok else "database unavailable",
        ),
        model=ComponentStatus(available=model.available, message=model.message),
    )

