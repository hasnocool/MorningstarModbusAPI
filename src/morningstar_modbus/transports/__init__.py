# src/morningstar_modbus/transports/__init__.py
"""Read-only Modbus RTU/TCP transport package."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.transports.core")
