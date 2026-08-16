# src/morningstar_modbus/_compat.py
"""Compatibility helpers used while legacy flat modules migrate into packages."""

from __future__ import annotations

import importlib
import sys
from collections.abc import MutableMapping
from types import ModuleType
from typing import Any


def alias_module(current_name: str, target_name: str) -> ModuleType:
    """Make a legacy module import resolve to the canonical implementation module."""

    module = importlib.import_module(target_name)
    sys.modules[current_name] = module
    return module


def export_module(namespace: MutableMapping[str, Any], target_name: str) -> ModuleType:
    """Expose a former flat module's symbols from its replacement package."""

    module = importlib.import_module(target_name)
    for name, value in vars(module).items():
        if not name.startswith("__"):
            namespace[name] = value

    public = getattr(module, "__all__", None)
    if public is None:
        public = tuple(name for name in vars(module) if not name.startswith("_"))
    namespace["__all__"] = public
    namespace["__getattr__"] = lambda name: getattr(module, name)
    namespace["__dir__"] = lambda: sorted(set(namespace) | set(dir(module)))
    return module
