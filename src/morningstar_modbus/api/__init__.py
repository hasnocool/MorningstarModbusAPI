# src/morningstar_modbus/api/__init__.py
"""HTTP API package with compatibility exports from the historical flat module."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.api.app")
