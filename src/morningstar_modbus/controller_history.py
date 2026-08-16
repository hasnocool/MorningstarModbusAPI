# src/morningstar_modbus/controller_history.py
"""Backward-compatible alias for retained-history orchestration."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.history.retained.service")
