"""
Global logger factory for SubFlow.

Usage:
    from utils.logger_config import get_logger
    logger = get_logger(__name__)
    logger.info("pipeline started", extra={"stage": "gmail_fetch"})
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "subflow.log"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
_BACKUP_COUNT = 5

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

_initialized = False


def _setup_root_logger() -> None:
    global _initialized
    if _initialized:
        return

    root = logging.getLogger("subflow")
    root.setLevel(_LOG_LEVEL)
    root.propagate = False

    # Console handler — always on
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_FORMATTER)
    root.addHandler(console)

    # Rotating file handler — skip if running in a read-only environment
    try:
        _LOG_DIR.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(_FORMATTER)
        root.addHandler(file_handler)
    except OSError:
        root.warning("Could not create log file at %s; file logging disabled.", _LOG_FILE)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'subflow' namespace."""
    _setup_root_logger()
    # Prefix every module logger so all SubFlow logs share the same handlers
    if not name.startswith("subflow"):
        name = f"subflow.{name}"
    return logging.getLogger(name)
