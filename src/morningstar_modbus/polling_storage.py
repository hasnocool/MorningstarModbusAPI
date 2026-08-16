# src/morningstar_modbus/polling_storage.py
"""Backward-compatible alias for polling-performance persistence."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.polling.storage")
