"""Owner-scoped memory inspection, modification, deletion, and access traces."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agent.runtime import get_memory_service
from app.api.imports import owner_context
from app.schemas.memory import (
    MemoryAccessListResponse,
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdateRequest,
)
from app.services.memory_service import MemoryService, MemoryServiceError

router = APIRouter(prefix="/memories", tags=["memories"])


def memory_service() -> MemoryService:
    return get_memory_service()


def _call(action):
    try:
        return action()
    except MemoryServiceError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.get("", response_model=MemoryListResponse)
def memories(
    scope: str | None = Query(default=None),
    owner_id: str = Depends(owner_context),
    service: MemoryService = Depends(memory_service),
) -> MemoryListResponse:
    if scope is not None and scope not in {"session", "long_term", "knowledge"}:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_MEMORY_SCOPE", "message": "记忆范围无效"},
        )
    return service.list(owner_id, scope)


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreateRequest,
    owner_id: str = Depends(owner_context),
    service: MemoryService = Depends(memory_service),
) -> MemoryResponse:
    return _call(
        lambda: service.remember(
            owner_id,
            payload.scope,
            payload.kind,
            payload.key,
            payload.value,
            expires_at=payload.expires_at,
        )
    )


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: str,
    payload: MemoryUpdateRequest,
    owner_id: str = Depends(owner_context),
    service: MemoryService = Depends(memory_service),
) -> MemoryResponse:
    return _call(
        lambda: service.update(
            owner_id,
            memory_id,
            payload.value,
            payload.expires_at,
        )
    )


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: str,
    owner_id: str = Depends(owner_context),
    service: MemoryService = Depends(memory_service),
) -> None:
    if not service.delete(owner_id, memory_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "MEMORY_NOT_FOUND", "message": "记忆不存在"},
        )


@router.get("/accesses", response_model=MemoryAccessListResponse)
def memory_accesses(
    owner_id: str = Depends(owner_context),
    service: MemoryService = Depends(memory_service),
) -> MemoryAccessListResponse:
    return service.list_accesses(owner_id)
