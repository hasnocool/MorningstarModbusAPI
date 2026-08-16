# src/morningstar_modbus/event_store.py
"""Backward-compatible alias for persistent event storage."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.persistence.events")
