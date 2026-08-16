# src/morningstar_modbus/system_semantics.py
"""Cross-product semantic metrics for system/site aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SystemAggregation = Literal["sum", "median", "max", "min", "latest", "state_set"]
SystemMetricCategory = Literal["solar", "battery", "energy", "temperature", "state", "health"]


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
        ("input_power_reported", "array_power", "pv_power", "solar_power", "input_power"),
        "Total instantaneous solar/PV input power contributed by participating controllers.",
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
        "Total charging current contributed toward the battery system.",
    ),
    SystemMetricSpec(
        "battery_voltage_v",
        "V",
        "median",
        "battery",
        ("battery_sense_voltage", "battery_terminal_voltage", "battery_voltage", "battery_voltage_1m"),
        "Representative battery-system voltage using the median of available bus observations.",
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
        "Total charging energy accumulated during the current controller day.",
    ),
    SystemMetricSpec(
        "daily_charge_ah",
        "Ah",
        "sum",
        "energy",
        ("daily_charge_ah", "charge_ah_daily", "daily_amp_hours"),
        "Total charging amp-hours accumulated during the current controller day.",
    ),
    SystemMetricSpec(
        "lifetime_charge_kwh",
        "kWh",
        "sum",
        "energy",
        ("charge_kwh_total", "lifetime_energy_kwh", "energy_total_kwh"),
        "Combined lifetime charging energy reported by participating charge controllers.",
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
    register_name: metric for metric in SYSTEM_METRICS for register_name in metric.registers
}


def metric_spec(name: str) -> SystemMetricSpec | None:
    return SYSTEM_METRIC_BY_NAME.get(name)


def metric_for_register(register_name: str) -> SystemMetricSpec | None:
    return SYSTEM_METRIC_BY_REGISTER.get(register_name)


def system_metric_catalog() -> list[dict[str, object]]:
    return [metric.to_dict() for metric in SYSTEM_METRICS]
