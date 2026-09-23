"""Owner-scoped Single-Agent HTTP API."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agent.runtime import get_agent_service
from app.agent.service import AgentService, AgentServiceError
from app.api.imports import owner_context
from app.llm.contracts import ModelProviderError
from app.schemas.agent import (
    AgentChatRequest,
    AgentComparisonRequest,
    AgentComparisonResponse,
    AgentRunResponse,
    AgentSessionListResponse,
    AgentSessionResponse,
)

router = APIRouter(prefix="/agent", tags=["agent"])


def agent_service() -> AgentService:
    try:
        return get_agent_service()
    except ModelProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


@router.post("/chat", response_model=AgentRunResponse)
def chat(
    payload: AgentChatRequest,
    owner_id: str = Depends(owner_context),
    service: AgentService = Depends(agent_service),
) -> AgentRunResponse:
    try:
        return service.chat(
            owner_id,
            payload.message,
            payload.session_id,
            workflow=payload.workflow,
        )
    except AgentServiceError as exc:
        http_status = 404 if exc.code == "AGENT_SESSION_NOT_FOUND" else 400
        raise HTTPException(
            status_code=http_status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.post("/compare", response_model=AgentComparisonResponse)
def compare_workflows(
    payload: AgentComparisonRequest,
    owner_id: str = Depends(owner_context),
    service: AgentService = Depends(agent_service),
) -> AgentComparisonResponse:
    try:
        return service.compare(owner_id, payload.message)
    except AgentServiceError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.get("/sessions", response_model=AgentSessionListResponse)
def sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    owner_id: str = Depends(owner_context),
    service: AgentService = Depends(agent_service),
) -> AgentSessionListResponse:
    return service.list_sessions(owner_id, page, page_size)


@router.get("/sessions/{session_id}", response_model=AgentSessionResponse)
def session_detail(
    session_id: str,
    owner_id: str = Depends(owner_context),
    service: AgentService = Depends(agent_service),
) -> AgentSessionResponse:
    item = service.get_session(owner_id, session_id)
    if item is None:
        raise _not_found("AGENT_SESSION_NOT_FOUND", "Agent 会话不存在")
    return item


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
def run_detail(
    run_id: str,
    owner_id: str = Depends(owner_context),
    service: AgentService = Depends(agent_service),
) -> AgentRunResponse:
    item = service.get_run(owner_id, run_id)
    if item is None:
        raise _not_found("AGENT_RUN_NOT_FOUND", "Agent 运行不存在")
    return item


@router.post("/runs/{run_id}/cancel", response_model=AgentRunResponse)
def cancel_run(
    run_id: str,
    owner_id: str = Depends(owner_context),
    service: AgentService = Depends(agent_service),
) -> AgentRunResponse:
    item = service.cancel_run(owner_id, run_id)
    if item is None:
        raise _not_found("AGENT_RUN_NOT_FOUND", "Agent 运行不存在")
    return item
