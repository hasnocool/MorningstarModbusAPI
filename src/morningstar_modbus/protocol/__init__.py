# src/morningstar_modbus/protocol/__init__.py
"""Read-only Modbus framing and parsing package."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.protocol.core")
