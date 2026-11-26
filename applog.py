"""Logging setup. Every module logs through the "ccm" logger family.

Importing this module does nothing noisy: until setup() is called the
loggers just discard messages, which keeps the unit tests quiet.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

import storage

ROOT_NAME = "ccm"
LOG_FILE = os.path.join(storage.BASE_DIR, "logs", "ccm.log")

logging.getLogger(ROOT_NAME).addHandler(logging.NullHandler())


def get(name):
    """Logger for a module, e.g. applog.get('manager') -> 'ccm.manager'."""
    return logging.getLogger(f"{ROOT_NAME}.{name}")


def setup(level=None, log_file=LOG_FILE):
    """Send log records to a rotating file. Level comes from CCM_LOG_LEVEL (default INFO)."""
    level_name = (level or os.environ.get("CCM_LOG_LEVEL", "INFO")).upper()
    root = logging.getLogger(ROOT_NAME)
    root.setLevel(getattr(logging, level_name, logging.INFO))

    already = any(isinstance(h, RotatingFileHandler) for h in root.handlers)
    if already:
        return root

    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    handler = RotatingFileHandler(log_file, maxBytes=500_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(handler)
    return root
