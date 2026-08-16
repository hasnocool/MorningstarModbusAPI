"""Regression checks for the canonical package-only source layout."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "morningstar_modbus"

LEGACY_FLAT_MODULES = {
    "_compat.py",
    "controller_api.py",
    "controller_data.py",
    "controller_history.py",
    "controller_history_liveview.py",
    "controller_history_providers.py",
    "controller_history_storage.py",
    "controller_history_types.py",
    "controller_inventory.py",
    "controller_scope.py",
    "event_store.py",
    "lifecycle.py",
    "polling_storage.py",
    "profiles.py",
    "replay.py",
    "snmp_traps.py",
    "storage.py",
    "system_api.py",
    "system_data.py",
    "system_semantics.py",
    "transport.py",
    "verification.py",
    "watcher.py",
}

REMOVED_MODULES = {
    f"morningstar_modbus.{name.removesuffix('.py')}" for name in LEGACY_FLAT_MODULES
} | {"morningstar_modbus.models", "morningstar_modbus.exceptions"}


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_package_root_contains_no_legacy_flat_modules() -> None:
    present = {path.name for path in PACKAGE_ROOT.glob("*.py")}
    assert not present.intersection(LEGACY_FLAT_MODULES)


def test_package_root_is_thin() -> None:
    assert {path.name for path in PACKAGE_ROOT.glob("*.py")} == {"__init__.py"}


def test_no_source_imports_reference_removed_modules() -> None:
    offenders: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        for imported in _imports(path):
            for removed in REMOVED_MODULES:
                if imported == removed or imported.startswith(f"{removed}."):
                    offenders.append(f"{path.relative_to(PACKAGE_ROOT)} -> {imported}")
    assert offenders == []
