from fastapi import FastAPI

from app.api.system import router as system_router


def create_app() -> FastAPI:
    app = FastAPI(title="Personal Finance Agent API", version="0.1.0")
    app.include_router(system_router, prefix="/api/v1")

    @app.get("/", tags=["system"])
    def root() -> dict[str, str]:
        return {"name": "personal-finance-agent", "status": "ok"}

    return app


app = create_app()

