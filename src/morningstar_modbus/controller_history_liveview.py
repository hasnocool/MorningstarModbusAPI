# src/morningstar_modbus/controller_history_liveview.py
"""Backward-compatible alias for the LiveView retained-history provider."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.history.retained.liveview")
