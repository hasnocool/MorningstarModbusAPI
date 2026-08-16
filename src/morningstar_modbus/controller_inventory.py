# src/morningstar_modbus/controller_inventory.py
"""Backward-compatible alias for controller inventory."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.controllers.inventory")
