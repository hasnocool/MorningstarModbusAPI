# src/morningstar_modbus/watcher.py
"""Backward-compatible alias for runtime watcher orchestration."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.runtime.watcher")
