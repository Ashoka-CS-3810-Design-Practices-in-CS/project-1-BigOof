"""Logging setup for the app.

Logs always go to stdout (which Vercel and gunicorn collect). Locally they're also
written to a rotating file in ``.logs/``; that's skipped on Vercel, whose filesystem
is read-only. Environment variables:

- ``LOG_LEVEL``: minimum level, default ``INFO``.
- ``LOG_DIR``: directory for the log file, default ``.logs`` in the working
  directory. Set it to an empty string to turn file logging off.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "big_o"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> logging.Logger:
    """Set up the ``big_o`` logger once and return it; safe to call repeatedly."""
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_big_o_configured", False):
        return logger

    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_dir = os.environ.get("LOG_DIR", ".logs")
    if log_dir and not os.environ.get("VERCEL"):
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                Path(log_dir) / "big_o.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.warning("File logging disabled, can't write to %s: %s", log_dir, exc)

    logger._big_o_configured = True
    return logger
