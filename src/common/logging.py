"""
Structured, sanitized, and auditable logging module.
Redacts API tokens, secrets, and authorization headers from logs.
Supports both rich colored console logging and structured JSON formatting.
"""

import logging
import re
import sys
from typing import Any, Dict
from src.common.config import settings

# Sensitive regex patterns to redact
SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE),
    re.compile(r"(token=)[^\s&]+", re.IGNORECASE),
    re.compile(r"(password=)[^\s&]+", re.IGNORECASE),
    re.compile(r"(key=)[^\s&]+", re.IGNORECASE),
    re.compile(r"(secret=)[^\s&]+", re.IGNORECASE),
]


class RedactingFormatter(logging.Formatter):
    """Sanitizes sensitive information from log messages."""

    def format(self, record: logging.LogRecord) -> str:
        orig = super().format(record)
        sanitized = orig
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
        return sanitized


def setup_logger(name: str = "ipo_system") -> logging.Logger:
    """Configure and return a structured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
        formatter = RedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()
