# src/morningstar_modbus/snmp_traps.py
"""Backward-compatible alias for SNMP trap ingestion."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.snmp.traps")
