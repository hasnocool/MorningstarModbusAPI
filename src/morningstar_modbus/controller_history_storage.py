# src/morningstar_modbus/controller_history_storage.py
"""Backward-compatible alias for retained-history persistence."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.history.retained.storage")
