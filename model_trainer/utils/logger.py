"""
Structured JSON logger for the training pipeline.
Logs to both console and rotating file.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timezone

from config.settings import LOGS_DIR

# Ensure stdout can handle UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class _Formatter(logging.Formatter):
    """Clean, readable log format with timestamps."""

    FORMATS = {
        logging.DEBUG:    "\033[90m%(asctime)s [DEBUG]    %(name)s - %(message)s\033[0m",
        logging.INFO:     "\033[36m%(asctime)s [INFO]     %(name)s - %(message)s\033[0m",
        logging.WARNING:  "\033[33m%(asctime)s [WARNING]  %(name)s - %(message)s\033[0m",
        logging.ERROR:    "\033[31m%(asctime)s [ERROR]    %(name)s - %(message)s\033[0m",
        logging.CRITICAL: "\033[1;31m%(asctime)s [CRITICAL] %(name)s - %(message)s\033[0m",
    }

    def format(self, record):
        fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.INFO])
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Create or retrieve a named logger.

    Writes to:
      - stdout (colored)
      - logs/trainer_YYYY-MM-DD.log (plain text)
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_Formatter())
    logger.addHandler(console)

    # File handler (one log file per day)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"trainer_{today}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    return logger
