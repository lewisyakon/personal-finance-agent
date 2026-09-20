from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.session import check_database
from app.llm.contracts import ModelProviderError
from app.llm.provider import create_model_provider

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
    provider = None
    try:
        provider = create_model_provider(settings)
        model = provider.health()
    except ModelProviderError as exc:
        model_available = False
        model_message = f"{exc.code}: {exc.message}"
    else:
        model_available = model.available
        model_message = model.message
    finally:
        close_provider = getattr(provider, "close", None)
        if callable(close_provider):
            close_provider()
    database_ok = check_database()
    return SystemStatus(
        app=ComponentStatus(available=True, message=f"mode={settings.app_mode}"),
        database=ComponentStatus(
            available=database_ok,
            message="sqlite ready" if database_ok else "database unavailable",
        ),
        model=ComponentStatus(available=model_available, message=model_message),
    )
