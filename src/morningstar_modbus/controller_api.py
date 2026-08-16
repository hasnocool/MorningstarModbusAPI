# src/morningstar_modbus/controller_api.py
"""Backward-compatible alias for the controller API router."""

from morningstar_modbus._compat import alias_module

alias_module(__name__, "morningstar_modbus.api.routers.controllers")
