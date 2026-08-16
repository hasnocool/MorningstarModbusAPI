# src/morningstar_modbus/controller_history_types.py
"""Backward-compatible alias for retained-history data types."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.history.retained.types")
