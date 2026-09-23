import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.agent.runtime import close_agent_runtime
from app.api.agent import router as agent_router
from app.api.data_management import router as data_management_router
from app.api.developer import router as developer_router
from app.api.imports import router as imports_router
from app.api.memory import router as memory_router
from app.api.planning import budget_router, confirmation_router
from app.api.semantic import router as semantic_router
from app.api.stats import router as stats_router
from app.api.system import router as system_router
from app.api.transactions import router as transactions_router
from app.core.config import get_settings
from app.db.init import init_database
from app.db.session import SessionLocal
from app.services.import_service import cleanup_expired_raw_files
from app.services.stats_service import StatsServiceError

_REQUEST_VALIDATION_CODES = {
    "from": ("INVALID_DATE", "日期格式无效，请使用 ISO-8601"),
    "to": ("INVALID_DATE", "日期格式无效，请使用 ISO-8601"),
    "compare_from": ("INVALID_DATE", "日期格式无效，请使用 ISO-8601"),
    "compare_to": ("INVALID_DATE", "日期格式无效，请使用 ISO-8601"),
    "budget_minor": ("INVALID_BUDGET", "预算金额必须是非负整数最小货币单位"),
    "comparison_budget_minor": ("INVALID_BUDGET", "预算金额必须是非负整数最小货币单位"),
    "threshold_minor": ("INVALID_THRESHOLD", "大额交易阈值必须是非负整数最小货币单位"),
    "limit": ("INVALID_LIMIT", "数量必须是 1 到 100 之间的整数"),
    "page": ("INVALID_LIMIT", "页码必须是正整数"),
    "page_size": ("INVALID_LIMIT", "页面大小必须是 1 到 100 之间的整数"),
}


def _request_validation_detail(exc: RequestValidationError) -> dict[str, dict[str, str]]:
    """Return a stable error shape without exposing Pydantic internals."""

    for error in exc.errors():
        location = error.get("loc") or ()
        field = str(location[-1]) if location else ""
        if field in _REQUEST_VALIDATION_CODES:
            code, message = _REQUEST_VALIDATION_CODES[field]
            return {"detail": {"code": code, "message": message}}
    return {
        "detail": {
            "code": "INVALID_REQUEST",
            "message": "请求参数无效，请检查参数格式和取值范围",
        }
    }


def create_app() -> FastAPI:
    settings = get_settings()
    init_database()
    # Enforce the raw-file TTL on every local process start as well as after a
    # completed import, so abandoned uploads do not live indefinitely.
    with SessionLocal() as db:
        cleanup_expired_raw_files(db)

    async def raw_file_cleanup_loop() -> None:
        interval_seconds = min(max(settings.raw_file_ttl_minutes * 60, 60), 3600)
        while True:
            await asyncio.sleep(interval_seconds)
            with SessionLocal() as db:
                cleanup_expired_raw_files(db)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        cleanup_task = asyncio.create_task(raw_file_cleanup_loop())
        try:
            yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            close_agent_runtime()

    app = FastAPI(
        title="Personal Finance Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
        www_redirect=False,
    )
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(imports_router, prefix="/api/v1")
    app.include_router(transactions_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(semantic_router, prefix="/api/v1")
    app.include_router(budget_router, prefix="/api/v1")
    app.include_router(confirmation_router, prefix="/api/v1")
    app.include_router(developer_router, prefix="/api/v1")
    app.include_router(memory_router, prefix="/api/v1")
    app.include_router(data_management_router, prefix="/api/v1")

    @app.exception_handler(StatsServiceError)
    async def stats_validation_error(_request: Request, exc: StatsServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": {"code": "STATS_VALIDATION_ERROR", "message": str(exc)}},
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content=_request_validation_detail(exc))

    @app.get("/", tags=["system"])
    def root() -> dict[str, str]:
        return {"name": "personal-finance-agent", "status": "ok"}

    return app


app = create_app()
