"""FastAPI application factory for the modular monolith."""

import structlog
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import TraceIdMiddleware
from app.health.routes import router as health_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(title="Citizenship Platform", version="0.1.0")
    app.add_middleware(TraceIdMiddleware)
    app.include_router(health_router)

    structlog.get_logger().info("app.startup", environment=settings.environment)
    return app


app = create_app()
