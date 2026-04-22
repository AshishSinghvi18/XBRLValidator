"""Structured logging configuration using ``structlog``.

Provides a ``configure_logging`` entry point that sets up structured
JSON logging for production and human-readable coloured logging for
development.

References:
    - structlog documentation: https://www.structlog.org/
    - OpenTelemetry trace context propagation
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(
    *,
    level: str = "INFO",
    json_format: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure structured logging for the validator.

    Call this once at application startup.

    Args:
        level:       Log level name (``"DEBUG"``, ``"INFO"``, ``"WARNING"``,
                     ``"ERROR"``, ``"CRITICAL"``).
        json_format: If ``True``, emit JSON log lines (production).
                     If ``False``, emit coloured console output (development).
        log_file:    Optional file path to write logs to (in addition to stderr).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors applied to every log event
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplication
    root_logger.handlers.clear()

    # stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(log_level)
    root_logger.addHandler(stderr_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)


def get_logger(name: str, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Get a named, structured logger.

    Args:
        name:            Logger name (typically ``__name__``).
        **initial_context: Key-value pairs bound to every log event from
                           this logger.

    Returns:
        A ``structlog`` bound logger.

    Examples:
        >>> log = get_logger(__name__, component="parser")
        >>> log.info("parsing started", file="instance.xml")
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger
