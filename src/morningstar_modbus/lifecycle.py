# src/morningstar_modbus/lifecycle.py
"""Backward-compatible alias for controller lifecycle."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.controllers.lifecycle")
