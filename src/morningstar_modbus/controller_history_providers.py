# src/morningstar_modbus/controller_history_providers.py
"""Backward-compatible alias for retained-history provider dispatch."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.history.retained.providers")
