# tests/test_package_layout.py
"""Regression coverage for domain-package compatibility imports."""

from __future__ import annotations

import importlib

import pytest


PACKAGE_EXPORTS = (
    ("morningstar_modbus.api", "morningstar_modbus.api.app"),
    ("morningstar_modbus.capture", "morningstar_modbus.capture.recorder"),
    ("morningstar_modbus.cli", "morningstar_modbus.cli.main"),
    ("morningstar_modbus.config", "morningstar_modbus.config.core"),
    ("morningstar_modbus.discovery", "morningstar_modbus.discovery.service"),
    ("morningstar_modbus.history", "morningstar_modbus.history.query"),
    ("morningstar_modbus.polling", "morningstar_modbus.polling.core"),
    ("morningstar_modbus.protocol", "morningstar_modbus.protocol.core"),
)

STRICT_ALIASES = (
    ("morningstar_modbus.controller_api", "morningstar_modbus.api.routers.controllers"),
    ("morningstar_modbus.system_api", "morningstar_modbus.api.routers.systems"),
    ("morningstar_modbus.controller_inventory", "morningstar_modbus.controllers.inventory"),
    ("morningstar_modbus.controller_scope", "morningstar_modbus.controllers.scope"),
    ("morningstar_modbus.lifecycle", "morningstar_modbus.controllers.lifecycle"),
    ("morningstar_modbus.controller_data", "morningstar_modbus.history.controller_data"),
    ("morningstar_modbus.controller_history", "morningstar_modbus.history.retained.service"),
    ("morningstar_modbus.controller_history_liveview", "morningstar_modbus.history.retained.liveview"),
    ("morningstar_modbus.controller_history_providers", "morningstar_modbus.history.retained.providers"),
    ("morningstar_modbus.controller_history_storage", "morningstar_modbus.history.retained.storage"),
    ("morningstar_modbus.controller_history_types", "morningstar_modbus.history.retained.types"),
    ("morningstar_modbus.storage", "morningstar_modbus.persistence.core"),
    ("morningstar_modbus.event_store", "morningstar_modbus.persistence.events"),
    ("morningstar_modbus.polling_storage", "morningstar_modbus.polling.storage"),
    ("morningstar_modbus.replay", "morningstar_modbus.capture.replay"),
    ("morningstar_modbus.verification", "morningstar_modbus.capture.verification"),
    ("morningstar_modbus.watcher", "morningstar_modbus.runtime.watcher"),
    ("morningstar_modbus.snmp_traps", "morningstar_modbus.snmp.traps"),
    ("morningstar_modbus.system_data", "morningstar_modbus.systems.data"),
    ("morningstar_modbus.system_semantics", "morningstar_modbus.systems.semantics"),
    ("morningstar_modbus.transport", "morningstar_modbus.transports.core"),
)


@pytest.mark.parametrize(("package_name", "implementation_name"), PACKAGE_EXPORTS)
def test_replacement_packages_export_flat_module_symbols(
    package_name: str,
    implementation_name: str,
) -> None:
    package = importlib.import_module(package_name)
    implementation = importlib.import_module(implementation_name)

    for name, value in vars(implementation).items():
        if name.startswith("__"):
            continue
        assert getattr(package, name) is value


@pytest.mark.parametrize(("legacy_name", "canonical_name"), STRICT_ALIASES)
def test_legacy_modules_resolve_to_canonical_implementation(
    legacy_name: str,
    canonical_name: str,
) -> None:
    legacy = importlib.import_module(legacy_name)
    canonical = importlib.import_module(canonical_name)
    assert legacy is canonical
