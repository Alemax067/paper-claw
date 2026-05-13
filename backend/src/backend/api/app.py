from __future__ import annotations

from fastapi import FastAPI

from backend.api.errors import register_error_handlers
from backend.api.routers import agent, artifacts, human_loop, read_models


def create_app() -> FastAPI:
    app = FastAPI(title="Paper Claw API")
    register_error_handlers(app)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(read_models.router, prefix="/api")
    app.include_router(human_loop.router, prefix="/api")
    app.include_router(artifacts.router, prefix="/api")
    app.include_router(agent.router, prefix="/api")
    return app
