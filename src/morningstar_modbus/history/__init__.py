# src/morningstar_modbus/history/__init__.py
"""Telemetry-history query and retained-history package."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.history.query")
