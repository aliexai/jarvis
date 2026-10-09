"""Structured logging for NOVA.

Configures the ``nova`` logger with a rotating file handler and an optional
console handler. Every handler carries :class:`RedactingFilter`, so secret
material cannot reach a log sink even if a caller logs it by accident.

Libraries are deliberately kept quiet: only the ``nova`` logger is configured,
and the root logger is left at WARNING.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from nova.config.paths import AppPaths, get_paths
from nova.security.redaction import RedactingFilter

LOGGER_NAME = "nova"
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 5


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the ``nova`` logger."""
    if not name or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def setup_logging(
    paths: AppPaths | None = None,
    *,
    level: str | int = "INFO",
    console: bool = True,
    max_bytes: int = _MAX_BYTES,
    backup_count: int = _BACKUP_COUNT,
) -> logging.Logger:
    """Configure and return the ``nova`` logger. Idempotent."""
    resolved = (paths or get_paths()).ensure()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(_coerce_level(level))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    redactor = RedactingFilter()

    file_handler = RotatingFileHandler(
        resolved.log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.addFilter(redactor)
        logger.addHandler(console_handler)

    logging.getLogger("nova").debug("logging initialised at %s", Path(resolved.log_file))
    return logger


def _coerce_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    return logging.getLevelNamesMapping().get(str(level).upper(), logging.INFO)


def shutdown_logging() -> None:
    """Flush and detach all handlers on the ``nova`` logger."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
