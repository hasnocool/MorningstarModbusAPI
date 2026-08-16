# src/morningstar_modbus/discovery/__init__.py
"""Transport discovery package."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.discovery.service")
