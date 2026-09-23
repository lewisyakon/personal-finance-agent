"""Process-local construction and cleanup for the stage 5 Agent service."""

from functools import lru_cache

from app.agent.multi_agent import MultiAgent
from app.agent.planner import PlannerAgent
from app.agent.service import AgentService
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.llm.provider import create_model_provider
from app.services.budget_service import BudgetService
from app.services.memory_service import MemoryService
from app.services.semantic_service import SemanticClassificationService
from app.tools.runtime import ToolExecutor


@lru_cache
def get_memory_service() -> MemoryService:
    return MemoryService(SessionLocal)


@lru_cache
def get_agent_service() -> AgentService:
    settings = get_settings()
    provider = create_model_provider(settings)
    tool_executor = ToolExecutor(
        SessionLocal,
        timeout_seconds=settings.tool_timeout_seconds,
        max_result_bytes=settings.tool_max_result_bytes,
    )
    memory_service = get_memory_service()
    budget_service = BudgetService(SessionLocal, tool_executor, memory_service)
    return AgentService(
        SessionLocal,
        provider,
        tool_executor,
        settings=settings,
        multi_agent_factory=lambda: MultiAgent(
            provider,
            tool_executor,
            SessionLocal,
            settings=settings,
        ),
        planner_agent_factory=lambda: PlannerAgent(
            provider,
            tool_executor,
            SessionLocal,
            budget_service,
            settings=settings,
            memory_service=memory_service,
        ),
        unverified_multi_agent_factory=lambda: MultiAgent(
            provider,
            tool_executor,
            SessionLocal,
            settings=settings,
            verification_enabled=False,
        ),
    )


@lru_cache
def get_budget_service() -> BudgetService:
    agent_service = get_agent_service()
    return BudgetService(
        SessionLocal,
        agent_service.tool_executor,
        get_memory_service(),
    )


@lru_cache
def get_semantic_service() -> SemanticClassificationService:
    agent_service = get_agent_service()
    return SemanticClassificationService(
        SessionLocal,
        agent_service.provider,
        agent_service.tool_executor,
        settings=agent_service.settings,
        memory_service=get_memory_service(),
    )


def close_agent_runtime() -> None:
    """Release resources only when the lazy runtime was actually constructed."""

    if get_agent_service.cache_info().currsize:
        service = get_agent_service()
        service.tool_executor.close(wait=False)
        close_provider = getattr(service.provider, "close", None)
        if callable(close_provider):
            close_provider()
    get_semantic_service.cache_clear()
    get_budget_service.cache_clear()
    get_memory_service.cache_clear()
    get_agent_service.cache_clear()
