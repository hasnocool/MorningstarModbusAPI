# src/morningstar_modbus/verification.py
"""Backward-compatible alias for capture verification."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.capture.verification")
