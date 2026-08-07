"""Tests de SMO Bingo (stdlib unittest).

Ejecutar desde la raíz del repo:

    python -m unittest discover -s Tests -t . -v
"""
from __future__ import annotations

import sys
from pathlib import Path

_FILES = Path(__file__).resolve().parent.parent / "Files"
_files_str = str(_FILES)
if _files_str not in sys.path:
    sys.path.insert(0, _files_str)
