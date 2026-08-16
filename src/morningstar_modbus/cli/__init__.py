# src/morningstar_modbus/cli/__init__.py
"""Command-line interface package."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.cli.main")
