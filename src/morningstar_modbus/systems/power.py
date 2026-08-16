"""Read-only system power-flow and energy-ledger views."""

from __future__ import annotations

from dataclasses import dataclass

from morningstar_modbus.systems.components import SystemComponentService
from morningstar_modbus.systems.data import SystemDataRepository


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _metric(latest: dict[str, object], name: str) -> dict[str, object]:
    metrics = latest.get("metrics")
    if not isinstance(metrics, dict):
        return {
            "value": None,
            "unit": None,
            "quality": "empty",
            "status": "unknown",
            "sources": [],
        }
    payload = metrics.get(name)
    if not isinstance(payload, dict):
        return {
            "value": None,
            "unit": None,
            "quality": "empty",
            "status": "unknown",
            "sources": [],
        }
    result = dict(payload)
    result["status"] = "observed" if payload.get("value") is not None else "unknown"
    return result


def _derived(value: float | None, unit: str, *, formula: str) -> dict[str, object]:
    return {
        "value": value,
        "unit": unit,
        "quality": "derived" if value is not None else "empty",
        "status": "derived" if value is not None else "unknown",
        "formula": formula,
    }


def _unknown(unit: str | None, reason: str) -> dict[str, object]:
    return {
        "value": None,
        "unit": unit,
        "quality": "empty",
        "status": "unknown",
        "reason": reason,
    }


@dataclass(frozen=True, slots=True)
class LedgerField:
    value: float | None
    unit: str
    status: str
    quality: str
    source_metric: str | None = None
    formula: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "quality": self.quality,
            "source_metric": self.source_metric,
            "formula": self.formula,
            "reason": self.reason,
        }


class SystemPowerService:
    """Reconcile normalized telemetry into explicit, provenance-aware energy views."""

    def __init__(
        self,
        data: SystemDataRepository,
        components: SystemComponentService | None = None,
    ) -> None:
        self.data = data
        self.components = components or SystemComponentService(data)

    async def power_flow(self, identifier: str) -> dict[str, object]:
        latest = await self.data.latest(identifier)
        graph = await self.components.graph(identifier)

        solar = _metric(latest, "solar_input_power_w")
        charge_power = _metric(latest, "charge_output_power_w")
        charge_current = _metric(latest, "battery_charge_current_a")
        battery_voltage = _metric(latest, "battery_voltage_v")
        battery_soc = _metric(latest, "battery_soc_percent")

        solar_w = _number(solar.get("value"))
        charge_w = _number(charge_power.get("value"))
        residual_w = None
        efficiency = None
        if solar_w is not None and charge_w is not None:
            residual_w = solar_w - charge_w
            if solar_w > 0:
                efficiency = charge_w / solar_w * 100.0

        unknowns = [
            "battery net current/power requires a source-backed shunt/BMS measurement",
            "load power requires a source-backed load/inverter/shunt measurement",
            "generator/auxiliary-source power is not inferred from controller state alone",
        ]
        known_core = sum(value is not None for value in (solar_w, charge_w))
        if known_core == 0:
            quality = "empty"
        else:
            quality = "partial"

        return {
            "system_uid": latest["system_uid"],
            "observed_at": latest["observed_at"],
            "quality": quality,
            "basis": "controller-side observations",
            "sources": {
                "solar_input_power_w": solar,
                "generator_power_w": _unknown(
                    "W",
                    "No source-backed generator power metric is available.",
                ),
                "auxiliary_power_w": _unknown(
                    "W",
                    "No source-backed auxiliary-source power metric is available.",
                ),
            },
            "battery": {
                "voltage_v": battery_voltage,
                "charge_current_a": charge_current,
                "charge_power_w": charge_power,
                "soc_percent": battery_soc,
                "net_current_a": _unknown(
                    "A",
                    "Not derived from charger current because battery loads may be active.",
                ),
                "net_power_w": _unknown(
                    "W",
                    "Requires net battery-current/shunt evidence.",
                ),
            },
            "loads": {
                "dc_power_w": _unknown(
                    "W",
                    "No source-backed aggregate DC-load power metric is available.",
                ),
                "inverter_power_w": _unknown(
                    "W",
                    "No source-backed inverter power metric is available.",
                ),
            },
            "balance": {
                "controller_input_w": solar,
                "controller_charge_output_w": charge_power,
                "controller_power_residual_w": _derived(
                    residual_w,
                    "W",
                    formula="solar_input_power_w - charge_output_power_w",
                ),
                "controller_conversion_efficiency_percent": _derived(
                    efficiency,
                    "%",
                    formula="charge_output_power_w / solar_input_power_w * 100",
                ),
                "whole_system_residual_w": _unknown(
                    "W",
                    "Battery net flow and total load measurements are required.",
                ),
            },
            "component_summary": graph["summary"],
            "unknowns": unknowns,
        }

    async def energy_ledger(self, identifier: str) -> dict[str, object]:
        latest = await self.data.latest(identifier)
        daily_wh = _metric(latest, "daily_charge_wh")
        daily_kwh = _metric(latest, "daily_charge_kwh")
        daily_ah = _metric(latest, "daily_charge_ah")
        lifetime_kwh = _metric(latest, "lifetime_charge_kwh")

        charge_wh = _number(daily_wh.get("value"))
        charge_source = "daily_charge_wh"
        charge_quality = str(daily_wh.get("quality") or "empty")
        charge_status = "observed" if charge_wh is not None else "unknown"
        formula = None
        if charge_wh is None:
            charge_kwh = _number(daily_kwh.get("value"))
            if charge_kwh is not None:
                charge_wh = charge_kwh * 1000.0
                charge_source = "daily_charge_kwh"
                charge_quality = "derived"
                charge_status = "derived"
                formula = "daily_charge_kwh * 1000"

        battery_charge = LedgerField(
            value=charge_wh,
            unit="Wh",
            status=charge_status,
            quality=charge_quality,
            source_metric=charge_source if charge_wh is not None else None,
            formula=formula,
            reason=(
                None
                if charge_wh is not None
                else "No source-backed daily battery-charge energy counter is available."
            ),
        )
        unknown = (
            "No source-backed system-wide measurement is available; value is not inferred."
        )
        quality = "partial" if charge_wh is not None else "empty"

        return {
            "system_uid": latest["system_uid"],
            "observed_at": latest["observed_at"],
            "period": "controller day",
            "quality": quality,
            "flows": {
                "solar_generated_wh": LedgerField(
                    None,
                    "Wh",
                    "unknown",
                    "empty",
                    reason=unknown,
                ).to_dict(),
                "generator_generated_wh": LedgerField(
                    None,
                    "Wh",
                    "unknown",
                    "empty",
                    reason=unknown,
                ).to_dict(),
                "battery_charge_wh": battery_charge.to_dict(),
                "battery_discharge_wh": LedgerField(
                    None,
                    "Wh",
                    "unknown",
                    "empty",
                    reason=unknown,
                ).to_dict(),
                "load_consumption_wh": LedgerField(
                    None,
                    "Wh",
                    "unknown",
                    "empty",
                    reason=unknown,
                ).to_dict(),
                "conversion_losses_wh": LedgerField(
                    None,
                    "Wh",
                    "unknown",
                    "empty",
                    reason=(
                        "Instantaneous controller residuals are not integrated into energy "
                        "without source-backed interval coverage."
                    ),
                ).to_dict(),
                "unaccounted_energy_wh": LedgerField(
                    None,
                    "Wh",
                    "unknown",
                    "empty",
                    reason=(
                        "A complete energy balance requires source, battery-discharge, and "
                        "load energy measurements."
                    ),
                ).to_dict(),
            },
            "counters": {
                "daily_charge_ah": daily_ah,
                "daily_charge_kwh": daily_kwh,
                "lifetime_charge_kwh": lifetime_kwh,
            },
        }
