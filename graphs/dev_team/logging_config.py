"""
Structured Logging Configuration
=================================

Configures ``structlog`` for the application.

- **LOCAL** mode  → coloured console output (``ConsoleRenderer``)
- **PRODUCTION** mode → JSON lines (``JSONRenderer``)

Call ``configure_logging()`` once at startup (e.g. in ``graph.py``).
All modules then use ``structlog.get_logger()`` instead of
``logging.getLogger(__name__)``.
"""

import logging
import os

import structlog


def configure_logging() -> None:
    """Configure structlog for the application.

    Reads ``ENV_MODE`` and ``LOG_LEVEL`` from the environment and sets up
    the appropriate renderer.
    """
    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()
    log_level = os.getenv("LOG_LEVEL", "DEBUG" if env_mode == "LOCAL" else "INFO")

    # --- stdlib baseline ---------------------------------------------------
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(message)s",
    )

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # --- structlog pipeline ------------------------------------------------
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if env_mode == "LOCAL":
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
