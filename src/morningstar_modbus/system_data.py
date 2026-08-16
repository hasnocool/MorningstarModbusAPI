# src/morningstar_modbus/system_data.py
"""Backward-compatible alias for system/site aggregation."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.systems.data")
