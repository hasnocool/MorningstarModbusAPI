# src/morningstar_modbus/system_semantics.py
"""Cross-product semantic metrics for system/site aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SystemAggregation = Literal["sum", "median", "max", "min", "latest", "state_set"]
SystemMetricCategory = Literal[
    "solar",
    "battery",
    "load",
    "energy",
    "temperature",
    "state",
    "health",
]


@dataclass(frozen=True, slots=True)
class SystemMetricSpec:
    """Normalized metric and ordered semantic-register aliases that can supply it."""

    name: str
    unit: str | None
    aggregation: SystemAggregation
    category: SystemMetricCategory
    registers: tuple[str, ...]
    description: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "unit": self.unit,
            "aggregation": self.aggregation,
            "category": self.category,
            "registers": list(self.registers),
            "description": self.description,
        }


SYSTEM_METRICS: tuple[SystemMetricSpec, ...] = (
    SystemMetricSpec(
        "solar_input_power_w",
        "W",
        "sum",
        "solar",
        ("input_power", "array_power", "pv_power", "solar_power", "input_power_reported"),
        (
            "Total instantaneous solar/PV input power contributed by participating controllers. "
            "A reconciled operational input-power value is preferred over a raw reported estimate "
            "when a profile exposes both."
        ),
    ),
    SystemMetricSpec(
        "charge_output_power_w",
        "W",
        "sum",
        "battery",
        ("output_power", "charge_power", "battery_charge_power"),
        "Total instantaneous charging output power delivered toward the battery system.",
    ),
    SystemMetricSpec(
        "battery_charge_current_a",
        "A",
        "sum",
        "battery",
        ("battery_charge_current", "charge_current", "output_current"),
        "Total controller-local charging current contributed toward the battery system.",
    ),
    SystemMetricSpec(
        "system_charge_current_a",
        "A",
        "median",
        "battery",
        ("system_charge_current",),
        (
            "Morningstar-reported whole-system charging current. Multiple reporters are treated "
            "as parallel observations of one system quantity and are never summed."
        ),
    ),
    SystemMetricSpec(
        "battery_net_current_a",
        "A",
        "median",
        "battery",
        ("system_battery_current",),
        (
            "Morningstar-reported whole-system battery current. This is distinct from charger "
            "output current and is never synthesized from charger current."
        ),
    ),
    SystemMetricSpec(
        "system_load_current_a",
        "A",
        "median",
        "load",
        ("system_load_current",),
        (
            "Morningstar-reported whole-system load current. Multiple reporters are resolved as "
            "observations of one system quantity rather than additive branch currents."
        ),
    ),
    SystemMetricSpec(
        "battery_voltage_v",
        "V",
        "median",
        "battery",
        (
            "battery_sense_voltage",
            "battery_terminal_voltage",
            "battery_voltage",
            "battery_voltage_1m",
        ),
        "Representative battery-system voltage using the median of available bus observations.",
    ),
    SystemMetricSpec(
        "load_voltage_v",
        "V",
        "median",
        "load",
        ("load_voltage",),
        "Representative source-backed load-terminal voltage when available.",
    ),
    SystemMetricSpec(
        "array_voltage_v",
        "V",
        "max",
        "solar",
        ("array_voltage", "pv_voltage", "solar_voltage"),
        "Highest active array/PV voltage observed across participating controllers.",
    ),
    SystemMetricSpec(
        "battery_soc_percent",
        "%",
        "median",
        "battery",
        ("battery_soc", "batt_soc", "state_of_charge", "soc"),
        "Representative battery state of charge when available.",
    ),
    SystemMetricSpec(
        "battery_temperature_c",
        "C",
        "median",
        "temperature",
        ("battery_temp", "battery_temperature", "rts_temp"),
        "Representative battery temperature across available controller sensors.",
    ),
    SystemMetricSpec(
        "daily_charge_wh",
        "Wh",
        "sum",
        "energy",
        ("daily_charge_wh", "charge_wh_daily", "daily_energy_wh"),
        "Total controller-local charging energy accumulated during the current controller day in Wh.",
    ),
    SystemMetricSpec(
        "daily_charge_kwh",
        "kWh",
        "sum",
        "energy",
        ("daily_charge_kwh", "internal_charge_kwh_daily"),
        "Total controller-local charging energy accumulated during the current day in kWh.",
    ),
    SystemMetricSpec(
        "daily_charge_ah",
        "Ah",
        "sum",
        "energy",
        (
            "daily_charge_ah",
            "charge_ah_daily",
            "daily_amp_hours",
            "internal_charge_ah_daily",
        ),
        "Total controller-local charging amp-hours accumulated during the current day.",
    ),
    SystemMetricSpec(
        "lifetime_charge_kwh",
        "kWh",
        "sum",
        "energy",
        (
            "charge_kwh_total",
            "lifetime_energy_kwh",
            "energy_total_kwh",
            "internal_charge_kwh_total",
        ),
        "Combined lifetime controller-local charging energy.",
    ),
    SystemMetricSpec(
        "system_charge_kwh_daily",
        "kWh",
        "median",
        "energy",
        ("system_charge_kwh_daily",),
        (
            "Morningstar whole-system charge-energy counter for the current day. Multiple "
            "reporters are treated as observations of one counter and are not summed."
        ),
    ),
    SystemMetricSpec(
        "system_charge_ah_daily",
        "Ah",
        "median",
        "energy",
        ("system_charge_ah_daily",),
        "Morningstar whole-system charge amp-hours for the current day.",
    ),
    SystemMetricSpec(
        "system_battery_ah_daily",
        "Ah",
        "median",
        "energy",
        ("system_battery_ah_daily",),
        "Morningstar whole-system signed battery net amp-hours for the current day.",
    ),
    SystemMetricSpec(
        "system_load_ah_daily",
        "Ah",
        "median",
        "energy",
        ("system_load_ah_daily",),
        "Morningstar whole-system load amp-hours for the current day.",
    ),
    SystemMetricSpec(
        "external_source_charge_kwh_daily",
        "kWh",
        "median",
        "energy",
        ("aggregated_shunt_charge_kwh_daily",),
        "Aggregated external-source shunt charge energy for the current day.",
    ),
    SystemMetricSpec(
        "external_source_charge_ah_daily",
        "Ah",
        "median",
        "energy",
        ("aggregated_shunt_charge_ah_daily",),
        "Aggregated external-source shunt charge amp-hours for the current day.",
    ),
    SystemMetricSpec(
        "shunt_battery_net_ah_daily",
        "Ah",
        "median",
        "energy",
        ("aggregated_shunt_battery_ah_daily",),
        "Aggregated shunt signed battery net amp-hours for the current day.",
    ),
    SystemMetricSpec(
        "shunt_load_ah_daily",
        "Ah",
        "median",
        "energy",
        ("aggregated_shunt_load_ah_daily",),
        "Aggregated shunt load amp-hours for the current day.",
    ),
    SystemMetricSpec(
        "charge_state",
        None,
        "state_set",
        "state",
        ("charge_state", "charger_state"),
        "Set of charge states currently reported across participating controllers.",
    ),
    SystemMetricSpec(
        "faults",
        None,
        "state_set",
        "health",
        ("faults", "fault_state", "active_faults"),
        "Current device-health fault state values reported by participating controllers.",
    ),
    SystemMetricSpec(
        "alarms",
        None,
        "state_set",
        "health",
        ("alarms", "alarm_state", "active_alarms"),
        "Current device-health alarm state values reported by participating controllers.",
    ),
)

SYSTEM_METRIC_BY_NAME = {metric.name: metric for metric in SYSTEM_METRICS}
SYSTEM_METRIC_BY_REGISTER = {
    register_name: metric
    for metric in SYSTEM_METRICS
    for register_name in metric.registers
}


def metric_spec(name: str) -> SystemMetricSpec | None:
    return SYSTEM_METRIC_BY_NAME.get(name)


def metric_for_register(register_name: str) -> SystemMetricSpec | None:
    return SYSTEM_METRIC_BY_REGISTER.get(register_name)


def system_metric_catalog() -> list[dict[str, object]]:
    return [metric.to_dict() for metric in SYSTEM_METRICS]
