"""
Application entry point.
Boots the container, configures logging, starts the FastAPI/uvicorn server.
"""
from __future__ import annotations

import asyncio
import os
import sys


def main() -> None:
    """Start the MAIS server."""
    # Load settings
    from medical_ais.config.settings import Settings
    settings = Settings()

    # Configure logging first
    from medical_ais.core.logging_setup import configure_logging
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("mais.starting", version="1.0.0")

    # Configure LangSmith tracing if enabled
    if settings.langchain_tracing_v2 and settings.langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        logger.info("langsmith.tracing_enabled", project=settings.langsmith_project)

    # Build container and create app
    from medical_ais.core.container import Container
    from medical_ais.api.app import create_app

    container = Container(settings)
    app = create_app(container)

    # Start server
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=None,   # Use our structlog config
        access_log=False,  # Handled by RequestLoggingMiddleware
    )


if __name__ == "__main__":
    main()
