# src/morningstar_modbus/system_semantics.py
"""Backward-compatible alias for cross-product system semantics."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.systems.semantics")
