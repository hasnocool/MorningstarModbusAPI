# src/morningstar_modbus/snmp/__init__.py
"""Optional read-only SNMP event ingestion package."""

from morningstar_modbus._compat import export_module

export_module(globals(), "morningstar_modbus.snmp.traps")
