# src/morningstar_modbus/polling/__init__.py
"""Polling policy, benchmarking, and performance package."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.polling.core")
