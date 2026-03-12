"""Logging utilities for ImmiDock."""

from __future__ import annotations

import logging

from immidock.utils.i18n import translate
from immidock.utils.logfile import get_log_handler


class TranslatedLogger(logging.LoggerAdapter):
    """Logger adapter that translates message keys before logging."""

    def process(self, msg, kwargs):
        if isinstance(msg, str):
            msg = translate(msg)
        return msg, kwargs


def setup_logger(name: str = "immidock", level: str = "INFO") -> TranslatedLogger:
    """Create or retrieve a ImmiDock logger with consistent formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.addHandler(get_log_handler())
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return TranslatedLogger(logger, {})
