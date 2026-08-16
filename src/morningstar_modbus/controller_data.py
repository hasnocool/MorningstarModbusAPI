# src/morningstar_modbus/controller_data.py
"""Backward-compatible alias for controller-scoped history queries."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.history.controller_data")
