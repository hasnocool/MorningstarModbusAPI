# src/morningstar_modbus/persistence/__init__.py
"""SQLite/WAL persistence package."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.persistence.core")
