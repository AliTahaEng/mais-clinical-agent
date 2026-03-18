"""
FastAPI application factory.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from medical_ais.api.middleware import RequestLoggingMiddleware, setup_cors
from medical_ais.api.routes import router
from medical_ais.api.routes_admin import admin_router
from medical_ais.api.routes_approvals import approvals_router
from medical_ais.api.routes_auth import auth_router
from medical_ais.api.routes_stream import stream_router
from medical_ais.core.container import Container

logger = structlog.get_logger(__name__)


def create_app(container: Container) -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = container._settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await container.build()
        logger.info("app.startup_complete")
        yield
        await container.close()
        logger.info("app.shutdown_complete")

    app = FastAPI(
        title="Medical Autonomous Intelligence System",
        description=(
            "Graph RAG + Agentic RAG system for medical decision support "
            "with tiered autonomous action execution."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Store container on app state so routes can access it
    app.state.container = container

    # Middleware
    app.add_middleware(RequestLoggingMiddleware)
    setup_cors(app, settings.allowed_origins)

    # Routes
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(router, prefix="/api/v1")
    app.include_router(stream_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error("app.unhandled_exception", error=str(exc), path=str(request.url))
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return app
