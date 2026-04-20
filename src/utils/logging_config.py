"""Structured logging configuration — Rule 13.

Uses ``structlog`` for JSON-formatted, machine-parseable log output.
Every pipeline stage logs: name, start_ts, end_ts, items_processed,
errors_found, memory_used_bytes, spill_occurred.  One log line per
fact is **prohibited** (log storms).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(
    *,
    level: int = logging.INFO,
    json_output: bool = True,
    log_file: str | None = None,
) -> None:
    """Set up structured logging for the XBRL Validator Engine.

    Args:
        level: Python logging level (e.g. ``logging.DEBUG``).
        json_output: If ``True``, emit JSON lines.  If ``False``, use
            coloured console output for development.
        log_file: Optional path to a log file.  When set, logs are
            written to the file *in addition to* stderr.

    This function is idempotent — calling it multiple times simply
    reconfigures the root logger.
    """
    # Shared processors for both stdlib and structlog.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    # -- stdlib root logger -------------------------------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to make this idempotent.
    root_logger.handlers.clear()

    # stderr handler
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Return a ``structlog`` bound logger with the given *name*.

    Args:
        name: Logger name (typically ``__name__``).
        **initial_context: Key-value pairs bound to every log entry.

    Returns:
        A bound ``structlog`` logger.
    """
    return structlog.get_logger(name, **initial_context)
