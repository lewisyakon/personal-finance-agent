from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.imports import router as imports_router
from app.api.stats import router as stats_router
from app.api.system import router as system_router
from app.api.transactions import router as transactions_router
from app.db.init import init_database
from app.db.session import SessionLocal
from app.services.import_service import cleanup_expired_raw_files
from app.services.stats_service import StatsServiceError


def create_app() -> FastAPI:
    init_database()
    # Enforce the raw-file TTL on every local process start as well as after a
    # completed import, so abandoned uploads do not live indefinitely.
    with SessionLocal() as db:
        cleanup_expired_raw_files(db)
    app = FastAPI(title="Personal Finance Agent API", version="0.1.0")
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(imports_router, prefix="/api/v1")
    app.include_router(transactions_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")

    @app.exception_handler(StatsServiceError)
    async def stats_validation_error(_request: Request, exc: StatsServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": {"code": "STATS_VALIDATION_ERROR", "message": str(exc)}},
        )

    @app.get("/", tags=["system"])
    def root() -> dict[str, str]:
        return {"name": "personal-finance-agent", "status": "ok"}

    return app


app = create_app()
