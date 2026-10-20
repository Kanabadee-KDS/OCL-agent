"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from ocl_api import __version__
from ocl_api.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="OCL Agent API", version=__version__)

    @app.get("/health")
    def health() -> dict[str, object]:
        s = get_settings()
        return {
            "status": "ok",
            "version": __version__,
            "llm_provider": s.llm_provider,
            "ollama_model": s.ollama_model if s.llm_provider == "ollama" else None,
        }

    return app


app = create_app()
