"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ocl_api import __version__
from ocl_api.api.auth import router as auth_router
from ocl_api.api.courses import router as courses_router
from ocl_api.api.curricula import router as curricula_router
from ocl_api.api.external import router as external_router
from ocl_api.api.flows import router as flows_router
from ocl_api.api.imports import router as imports_router
from ocl_api.api.m2 import router as m2_router
from ocl_api.api.persons import router as persons_router
from ocl_api.api.roles import router as roles_router
from ocl_api.api.skills import public as public_router
from ocl_api.api.skills import router as skills_router
from ocl_api.api.smo import router as smo_router
from ocl_api.api.users import router as users_router
from ocl_api.config import get_settings
from ocl_api.ingest.pdf_reader import find_tessdata


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
    app.include_router(courses_router)
    app.include_router(persons_router)
    app.include_router(smo_router)
    app.include_router(m2_router)
    app.include_router(skills_router)
    app.include_router(public_router)
    app.include_router(external_router)
    app.include_router(roles_router)
    app.include_router(users_router)
    app.include_router(flows_router)
    if s.database_url:
        from ocl_api.db import migrate

        migrate(s.database_url, s.database_schema)
        from ocl_api.sections import backfill

        backfill(s.database_url, s.database_schema)  # drafts made before migration 010
        from ocl_api.courses import CourseStore

        CourseStore(s.database_url, s.database_schema).backfill()  # the central courses, once

    @app.get("/health")
    def health() -> dict[str, object]:
        s = get_settings()
        return {
            "status": "ok",
            "version": __version__,
            "llm_provider": s.llm_provider,
            "ollama_model": s.ollama_model if s.llm_provider == "ollama" else None,
            "gemini_configured": bool(s.gemini_api_key),
            "gemini_model": s.gemini_model,
            "inline_worker": s.inline_worker,
            "database": "postgres" if s.database_url else "files",
            "ocr": s.ocr_language if (s.ocr and find_tessdata(s.ocr_language)) else None,
            "auth": "enabled" if s.auth_secret else "disabled",
        }

    return app


app = create_app()
