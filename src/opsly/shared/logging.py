"""Structured logging helpers."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s cid=%(correlation_id)s %(message)s",
        stream=sys.stdout,
    )
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        record.correlation_id = correlation_id_var.get() or "-"
        return record

    logging.setLogRecordFactory(record_factory)


def bind_context(*, correlation_id: str | None = None, session_id: str | None = None) -> None:
    if correlation_id is not None:
        correlation_id_var.set(correlation_id)
    if session_id is not None:
        session_id_var.set(session_id)
