"""Read-only system power-flow and energy-ledger views."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

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


def _resolved_system_metric(
    latest: dict[str, object],
    name: str,
    *,
    absolute_tolerance: float = 0.5,
    relative_tolerance: float = 0.05,
) -> dict[str, object]:
    """Resolve already-aggregated system observations without summing them.

    A single source is accepted directly. Multiple numeric reporters must agree
    within a small tolerance; otherwise the metric remains explicitly unknown
    because the user-defined API system may contain multiple electrical systems
    or stale/misconfigured reporters.
    """

    result = _metric(latest, name)
    sources = result.get("sources")
    if not isinstance(sources, list):
        return result
    values = [
        parsed
        for source in sources
        if isinstance(source, dict)
        and (parsed := _number(source.get("value"))) is not None
    ]
    if not values:
        return result
    if len(values) == 1:
        result["value"] = values[0]
        result["resolution"] = "single_source"
        result["status"] = "observed"
        return result

    center = float(median(values))
    tolerance = max(absolute_tolerance, abs(center) * relative_tolerance)
    spread = max(values) - min(values)
    if spread > tolerance:
        result["value"] = None
        result["quality"] = "conflict"
        result["status"] = "unknown"
        result["resolution"] = "conflict"
        result["reason"] = (
            f"Multiple whole-system observations disagree by {spread:.3f}, "
            f"exceeding the {tolerance:.3f} resolution tolerance."
        )
        return result

    result["value"] = center
    result["resolution"] = "consensus_median"
    result["status"] = "observed"
    return result


def _derived(
    value: float | None,
    unit: str,
    *,
    formula: str,
    inputs: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "value": value,
        "unit": unit,
        "quality": "derived" if value is not None else "empty",
        "status": "derived" if value is not None else "unknown",
        "formula": formula,
        "inputs": list(inputs),
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
        system_charge_current = _resolved_system_metric(latest, "system_charge_current_a")
        battery_net_current = _resolved_system_metric(latest, "battery_net_current_a")
        system_load_current = _resolved_system_metric(latest, "system_load_current_a")
        battery_voltage = _metric(latest, "battery_voltage_v")
        load_voltage = _metric(latest, "load_voltage_v")
        battery_soc = _metric(latest, "battery_soc_percent")

        solar_w = _number(solar.get("value"))
        charge_w = _number(charge_power.get("value"))
        system_charge_a = _number(system_charge_current.get("value"))
        battery_net_a = _number(battery_net_current.get("value"))
        load_a = _number(system_load_current.get("value"))
        battery_v = _number(battery_voltage.get("value"))
        load_v = _number(load_voltage.get("value"))

        controller_residual_w = None
        efficiency = None
        if solar_w is not None and charge_w is not None:
            controller_residual_w = solar_w - charge_w
            if solar_w > 0:
                efficiency = charge_w / solar_w * 100.0

        system_charge_w = (
            system_charge_a * battery_v
            if system_charge_a is not None and battery_v is not None
            else None
        )
        battery_net_w = (
            battery_net_a * battery_v
            if battery_net_a is not None and battery_v is not None
            else None
        )
        dc_load_w = load_a * load_v if load_a is not None and load_v is not None else None
        current_residual_a = (
            system_charge_a - battery_net_a - load_a
            if system_charge_a is not None and battery_net_a is not None and load_a is not None
            else None
        )
        whole_system_residual_w = (
            system_charge_w - battery_net_w - dc_load_w
            if system_charge_w is not None
            and battery_net_w is not None
            and dc_load_w is not None
            else None
        )

        unknowns = [
            "generator/auxiliary-source instantaneous power is not inferred from controller state alone",
        ]
        if battery_net_a is None:
            unknowns.append(
                "battery net current/power requires a resolved source-backed system or shunt measurement"
            )
        if load_a is None:
            unknowns.append(
                "load current/power requires a resolved source-backed system or shunt measurement"
            )
        if system_charge_a is None:
            unknowns.append(
                "whole-system charging current is unavailable or conflicting; "
                "controller-local charge remains separate"
            )

        known = (
            solar_w,
            charge_w,
            system_charge_a,
            battery_net_a,
            load_a,
        )
        quality = "empty" if all(value is None for value in known) else "partial"

        return {
            "system_uid": latest["system_uid"],
            "observed_at": latest["observed_at"],
            "quality": quality,
            "basis": "source-backed controller/system observations",
            "sources": {
                "solar_input_power_w": solar,
                "generator_power_w": _unknown(
                    "W",
                    "No source-backed generator power metric is available.",
                ),
                "auxiliary_power_w": _unknown(
                    "W",
                    "No source-backed instantaneous auxiliary-source power metric is available.",
                ),
            },
            "battery": {
                "voltage_v": battery_voltage,
                "charge_current_a": charge_current,
                "system_charge_current_a": system_charge_current,
                "charge_power_w": charge_power,
                "soc_percent": battery_soc,
                "net_current_a": battery_net_current,
                "net_power_w": _derived(
                    battery_net_w,
                    "W",
                    formula="battery_net_current_a * battery_voltage_v",
                    inputs=("battery_net_current_a", "battery_voltage_v"),
                ),
            },
            "loads": {
                "dc_current_a": system_load_current,
                "voltage_v": load_voltage,
                "dc_power_w": _derived(
                    dc_load_w,
                    "W",
                    formula="system_load_current_a * load_voltage_v",
                    inputs=("system_load_current_a", "load_voltage_v"),
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
                    controller_residual_w,
                    "W",
                    formula="solar_input_power_w - charge_output_power_w",
                    inputs=("solar_input_power_w", "charge_output_power_w"),
                ),
                "controller_conversion_efficiency_percent": _derived(
                    efficiency,
                    "%",
                    formula="charge_output_power_w / solar_input_power_w * 100",
                    inputs=("charge_output_power_w", "solar_input_power_w"),
                ),
                "system_charge_power_w": _derived(
                    system_charge_w,
                    "W",
                    formula="system_charge_current_a * battery_voltage_v",
                    inputs=("system_charge_current_a", "battery_voltage_v"),
                ),
                "system_current_residual_a": _derived(
                    current_residual_a,
                    "A",
                    formula=(
                        "system_charge_current_a - battery_net_current_a - "
                        "system_load_current_a"
                    ),
                    inputs=(
                        "system_charge_current_a",
                        "battery_net_current_a",
                        "system_load_current_a",
                    ),
                ),
                "whole_system_residual_w": _derived(
                    whole_system_residual_w,
                    "W",
                    formula=(
                        "system_charge_power_w - battery_net_power_w - dc_load_power_w"
                    ),
                    inputs=(
                        "system_charge_power_w",
                        "battery_net_power_w",
                        "dc_load_power_w",
                    ),
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

        system_charge_kwh = _resolved_system_metric(
            latest,
            "system_charge_kwh_daily",
            absolute_tolerance=0.05,
            relative_tolerance=0.02,
        )
        system_charge_ah = _resolved_system_metric(
            latest,
            "system_charge_ah_daily",
            absolute_tolerance=0.5,
            relative_tolerance=0.02,
        )
        system_battery_ah = _resolved_system_metric(
            latest,
            "system_battery_ah_daily",
            absolute_tolerance=0.5,
            relative_tolerance=0.02,
        )
        system_load_ah = _resolved_system_metric(
            latest,
            "system_load_ah_daily",
            absolute_tolerance=0.5,
            relative_tolerance=0.02,
        )
        external_source_kwh = _resolved_system_metric(
            latest,
            "external_source_charge_kwh_daily",
            absolute_tolerance=0.05,
            relative_tolerance=0.02,
        )
        external_source_ah = _resolved_system_metric(
            latest,
            "external_source_charge_ah_daily",
            absolute_tolerance=0.5,
            relative_tolerance=0.02,
        )
        shunt_battery_ah = _resolved_system_metric(
            latest,
            "shunt_battery_net_ah_daily",
            absolute_tolerance=0.5,
            relative_tolerance=0.02,
        )
        shunt_load_ah = _resolved_system_metric(
            latest,
            "shunt_load_ah_daily",
            absolute_tolerance=0.5,
            relative_tolerance=0.02,
        )

        charge_wh = None
        charge_source: str | None = None
        charge_quality = "empty"
        charge_status = "unknown"
        formula = None

        system_kwh = _number(system_charge_kwh.get("value"))
        if system_kwh is not None:
            charge_wh = system_kwh * 1000.0
            charge_source = "system_charge_kwh_daily"
            charge_quality = "derived"
            charge_status = "derived"
            formula = "system_charge_kwh_daily * 1000"
        else:
            charge_wh = _number(daily_wh.get("value"))
            if charge_wh is not None:
                charge_source = "daily_charge_wh"
                charge_quality = str(daily_wh.get("quality") or "empty")
                charge_status = "observed"
            else:
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
            source_metric=charge_source,
            formula=formula,
            reason=(
                None
                if charge_wh is not None
                else "No resolved source-backed daily battery-charge energy counter is available."
            ),
        )

        external_kwh = _number(external_source_kwh.get("value"))
        external_source_charge = LedgerField(
            value=external_kwh * 1000.0 if external_kwh is not None else None,
            unit="Wh",
            status="derived" if external_kwh is not None else "unknown",
            quality="derived" if external_kwh is not None else "empty",
            source_metric=(
                "external_source_charge_kwh_daily" if external_kwh is not None else None
            ),
            formula=(
                "external_source_charge_kwh_daily * 1000"
                if external_kwh is not None
                else None
            ),
            reason=(
                None
                if external_kwh is not None
                else "No resolved aggregated external-source shunt energy counter is available."
            ),
        )

        unknown = "No source-backed system-wide measurement is available; value is not inferred."
        quality = (
            "partial"
            if charge_wh is not None
            or external_kwh is not None
            or _number(system_battery_ah.get("value")) is not None
            or _number(system_load_ah.get("value")) is not None
            else "empty"
        )

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
                    reason=(
                        "External-source shunt energy is not labeled as generator energy because "
                        "the source may be a generator, charger, fuel cell, or other DC source."
                    ),
                ).to_dict(),
                "external_source_charge_wh": external_source_charge.to_dict(),
                "battery_charge_wh": battery_charge.to_dict(),
                "battery_discharge_wh": LedgerField(
                    None,
                    "Wh",
                    "unknown",
                    "empty",
                    reason=(
                        "Signed battery Ah counters do not provide separate discharge Wh without "
                        "time-resolved voltage/current or a source-backed discharge-energy counter."
                    ),
                ).to_dict(),
                "load_consumption_wh": LedgerField(
                    None,
                    "Wh",
                    "unknown",
                    "empty",
                    reason=(
                        "Load Ah counters are preserved natively and are not converted to Wh using "
                        "an unrelated instantaneous voltage."
                    ),
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
                "system_charge_ah_daily": system_charge_ah,
                "system_charge_kwh_daily": system_charge_kwh,
                "system_battery_ah_daily": system_battery_ah,
                "system_load_ah_daily": system_load_ah,
                "external_source_charge_ah_daily": external_source_ah,
                "external_source_charge_kwh_daily": external_source_kwh,
                "shunt_battery_net_ah_daily": shunt_battery_ah,
                "shunt_load_ah_daily": shunt_load_ah,
            },
        }
