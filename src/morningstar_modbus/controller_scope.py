# src/morningstar_modbus/controller_scope.py
"""Backward-compatible alias for controller scope."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.controllers.scope")
