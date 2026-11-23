"""Load the pure-Python modules without importing Home Assistant.

``custom_components/timotion_desk/__init__.py`` imports Home Assistant, so the
tests build a stand-in package that only exposes the directory.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "timotion_desk"
_PKG_NAME = "timotion_desk_pure"

if _PKG_NAME not in sys.modules:
    pkg = types.ModuleType(_PKG_NAME)
    pkg.__path__ = [str(_PKG_DIR)]
    sys.modules[_PKG_NAME] = pkg

protocol = importlib.import_module(f"{_PKG_NAME}.protocol")
motion = importlib.import_module(f"{_PKG_NAME}.motion")
