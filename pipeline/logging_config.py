"""Shared logging setup so every module logs in a consistent format."""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: int | str = logging.INFO) -> None:
    """Configure the root logger once.

    Safe to call multiple times - subsequent calls are no-ops. Logs go to
    stdout with timestamps and the module name so pipeline progress is easy
    to follow.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # ClearML is chatty at INFO; keep its noise down a notch.
    logging.getLogger("clearml").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, ensuring logging is configured first."""
    setup_logging()
    return logging.getLogger(name)
