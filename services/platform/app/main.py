"""FastAPI application factory for the modular monolith."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.applicants.routes import router as route_profile_router
from app.cases.routes import router as cases_router
from app.core.config import get_settings
from app.core.db import connection_is_superuser
from app.core.logging import configure_logging
from app.core.middleware import TraceIdMiddleware
from app.health.routes import router as health_router
from app.shared.errors import register_exception_handlers

_log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # RLS defence-in-depth only holds if the login role is a non-superuser (a superuser
    # bypasses RLS even under FORCE). Refuse to run a deployed environment as a
    # superuser; in local/CI the role is a throwaway superuser the migration demotes,
    # so only warn (ADR-0006, R1).
    settings = get_settings()
    if connection_is_superuser():
        detail = "DB login role is a superuser: RLS defence-in-depth is not enforced"
        if settings.environment == "local":
            _log.warning("rls.login_role_superuser", detail=detail)
        else:
            raise RuntimeError(detail)
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

    structlog.get_logger().info("app.startup", environment=settings.environment)
    return app


app = create_app()
