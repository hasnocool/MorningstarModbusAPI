# src/morningstar_modbus/intelligence/capabilities.py
"""Capability negotiation from catalog declarations and observed transport."""

from __future__ import annotations

from morningstar_modbus.catalog.types import DeviceProfileSpec
from morningstar_modbus.domain.models import Endpoint, RegisterValue


def negotiate_capabilities(
    spec: DeviceProfileSpec,
    *,
    endpoint: Endpoint | None = None,
    values: tuple[RegisterValue, ...] = (),
) -> tuple[str, ...]:
    capabilities = set(spec.capabilities)
    if endpoint is not None:
        capabilities.add("modbus_tcp" if endpoint.transport == "tcp" else "rtu")
    names = {value.name for value in values}
    if "battery_soc" in names or "soc" in names:
        capabilities.add("battery_soc")
    if any("load_state" == name for name in names):
        capabilities.add("load_control")
    if any(name.startswith("generator_") for name in names):
        capabilities.add("generator_control")
    if "rts_temp" in names:
        capabilities.add("remote_temperature_sensor")
    if "battery_sense_voltage" in names:
        capabilities.add("battery_voltage_sense")
    return tuple(sorted(capabilities))
