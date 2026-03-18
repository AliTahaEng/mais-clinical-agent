"""
FastAPI middleware: request logging, correlation IDs, CORS.
"""
from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with duration and correlation ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.monotonic()

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "request.unhandled_exception",
                request_id=request_id,
                path=request.url.path,
                error=str(exc),
            )
            raise

        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "request.complete",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        response.headers["X-Request-ID"] = request_id
        return response


def setup_cors(app, allowed_origins: list[str]) -> None:
    """Add CORS middleware with the configured allowed origins."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
