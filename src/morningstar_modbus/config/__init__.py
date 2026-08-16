# src/morningstar_modbus/config/__init__.py
"""Configuration package."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.config.core")
