"""Process-local construction and cleanup for the stage 5 Agent service."""

from functools import lru_cache

from app.agent.service import AgentService
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.llm.provider import create_model_provider
from app.tools.runtime import ToolExecutor


@lru_cache
def get_agent_service() -> AgentService:
    settings = get_settings()
    provider = create_model_provider(settings)
    tool_executor = ToolExecutor(
        SessionLocal,
        timeout_seconds=settings.tool_timeout_seconds,
        max_result_bytes=settings.tool_max_result_bytes,
    )
    return AgentService(
        SessionLocal,
        provider,
        tool_executor,
        settings=settings,
    )


def close_agent_runtime() -> None:
    """Release resources only when the lazy runtime was actually constructed."""

    if not get_agent_service.cache_info().currsize:
        return
    service = get_agent_service()
    service.tool_executor.close(wait=False)
    close_provider = getattr(service.provider, "close", None)
    if callable(close_provider):
        close_provider()
    get_agent_service.cache_clear()
