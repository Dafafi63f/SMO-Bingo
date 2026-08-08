"""Hooks pytest: borrar .pytest_cache al terminar la sesión."""
from __future__ import annotations

import shutil
from pathlib import Path

import catalog_lib  # noqa: F401  # atexit → clear_runtime_caches

_ROOT = Path(__file__).resolve().parent.parent


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    for cache in _ROOT.rglob(".pytest_cache"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)
