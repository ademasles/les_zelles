"""Centralized structured logging for Analyse-DCE."""

from __future__ import annotations

import logging
import sys


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    for logger_name in ("httpx", "httpcore", "PIL", "fitz", "urllib3"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
