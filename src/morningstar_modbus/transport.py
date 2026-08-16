# src/morningstar_modbus/transport.py
"""Backward-compatible alias for read-only Modbus transports."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.transports.core")
