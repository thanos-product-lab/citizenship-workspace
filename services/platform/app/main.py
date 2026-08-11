"""FastAPI application factory for the modular monolith."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.applicants.routes import router as route_profile_router
from app.assessments.routes import assessments_router, requirements_router
from app.cases.routes import router as cases_router
from app.core.config import get_settings
from app.core.db import connection_is_superuser
from app.core.logging import configure_logging
from app.core.middleware import TraceIdMiddleware
from app.health.routes import router as health_router
from app.residence.routes import router as application_dates_router
from app.residence.routes import travel_records_router
from app.shared.errors import register_exception_handlers

_log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # RLS is enforced per request via `SET ROLE app_rls`, which applies even when the
    # DB login role is a superuser. But a superuser login role means a query that
    # *forgot* to SET ROLE would bypass RLS, so the fail-closed backstop is not fully
    # enforced. Managed Postgres (e.g. Railway) connects as a superuser, so we warn
    # loudly rather than refuse to boot; a hard guarantee needs a dedicated
    # non-superuser login role (ADR-0006 R1, Option A).
    if connection_is_superuser():
        _log.warning(
            "rls.login_role_superuser",
            detail="DB login role is a superuser; RLS backstop relies on per-request SET ROLE only",
        )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(title="Citizenship Platform", version="0.1.0", lifespan=lifespan)
    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(TraceIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)
    app.include_router(cases_router)
    app.include_router(route_profile_router)
    app.include_router(application_dates_router)
    app.include_router(travel_records_router)
    app.include_router(requirements_router)
    app.include_router(assessments_router)

    structlog.get_logger().info("app.startup", environment=settings.environment)
    return app


app = create_app()
