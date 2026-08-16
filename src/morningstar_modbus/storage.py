# src/morningstar_modbus/storage.py
"""Backward-compatible alias for SQLite telemetry persistence."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.persistence.core")
