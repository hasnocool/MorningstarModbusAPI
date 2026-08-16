# src/morningstar_modbus/replay.py
"""Backward-compatible alias for capture replay."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.capture.replay")
