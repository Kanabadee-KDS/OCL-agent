"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ocl_api import __version__
from ocl_api.api.auth import router as auth_router
from ocl_api.api.curricula import router as curricula_router
from ocl_api.api.imports import router as imports_router
from ocl_api.config import get_settings


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="OCL Agent API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(imports_router)
    app.include_router(auth_router)
    app.include_router(curricula_router)
    if s.database_url:
        from ocl_api.db import migrate

        migrate(s.database_url, s.database_schema)

    @app.get("/health")
    def health() -> dict[str, object]:
        s = get_settings()
        return {
            "status": "ok",
            "version": __version__,
            "llm_provider": s.llm_provider,
            "ollama_model": s.ollama_model if s.llm_provider == "ollama" else None,
            "gemini_configured": bool(s.gemini_api_key),
            "inline_worker": s.inline_worker,
            "database": "postgres" if s.database_url else "files",
            "auth": "enabled" if s.auth_secret else "disabled",
        }

    return app


app = create_app()
