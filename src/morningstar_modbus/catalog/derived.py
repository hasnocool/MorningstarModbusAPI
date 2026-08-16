"""Derived telemetry that reconciles vendor-reported values without hiding raw evidence."""

from __future__ import annotations

from morningstar_modbus.models import RegisterValue

_INPUT_POWER_ADDRESS = 0x003B
_MIN_OUTPUT_FOR_RATIO_CHECK_W = 25.0
_MAX_INPUT_TO_OUTPUT_RATIO = 2.0
_MAX_INPUT_OUTPUT_MARGIN_W = 250.0
_MIN_INPUT_TO_OUTPUT_RATIO = 0.5


def _numeric(value: RegisterValue | None) -> float | None:
    if value is None or isinstance(value.value, bool):
        return None
    if isinstance(value.value, (int, float)):
        candidate = float(value.value)
        return candidate if candidate >= 0.0 else None
    return None


def _battery_side_power(values: dict[str, RegisterValue]) -> tuple[float | None, str]:
    """Return the best available battery-side power reference for plausibility checks."""

    output_power = _numeric(values.get("output_power"))
    if output_power is not None:
        return output_power, "controller_output_power"

    battery_voltage = _numeric(values.get("battery_voltage"))
    charge_current = _numeric(values.get("battery_charge_current"))
    if battery_voltage is not None and charge_current is not None:
        return battery_voltage * charge_current, "battery_voltage_x_charge_current"

    return None, "unavailable"


def _reported_input_is_suspect(reported: float, output_reference: float | None) -> bool:
    if output_reference is None:
        return False

    if output_reference < _MIN_OUTPUT_FOR_RATIO_CHECK_W:
        return reported > _MAX_INPUT_OUTPUT_MARGIN_W

    too_high = reported > max(
        output_reference * _MAX_INPUT_TO_OUTPUT_RATIO,
        output_reference + _MAX_INPUT_OUTPUT_MARGIN_W,
    )
    too_low = reported < output_reference * _MIN_INPUT_TO_OUTPUT_RATIO
    return too_high or too_low


def derive_register_values(
    profile_name: str,
    named_values: tuple[RegisterValue, ...],
) -> tuple[RegisterValue, ...]:
    """Add operator-facing derived values while retaining vendor-reported measurements.

    TriStar MPPT register 0x003B is decoded exactly as Morningstar documents it, but
    Morningstar also warns that array input current is not measured by precision shunts
    and that reported input power may therefore have significant error.  When that
    estimate conflicts severely with battery-side charging power, expose the battery-side
    output as a conservative operational proxy while keeping the original 0x003B value as
    ``input_power_reported``.
    """

    if profile_name != "tristar_mppt":
        return ()

    values = {value.name: value for value in named_values}
    reported_register = values.get("input_power_reported")
    reported = _numeric(reported_register)
    if reported_register is None or reported is None:
        return ()

    output_reference, output_source = _battery_side_power(values)
    suspect = _reported_input_is_suspect(reported, output_reference)

    if suspect and output_reference is not None:
        selected = output_reference
        source = "charge_output_proxy"
        quality = "estimated_from_output"
        note = (
            f"controller-reported input power {reported:.2f} W is inconsistent with "
            f"battery-side power {output_reference:.2f} W ({output_source}); using the "
            "battery-side value as a conservative operational proxy"
        )
    else:
        selected = reported
        source = "controller_reported"
        quality = "reported_unverified"
        note = (
            "Morningstar reports this input-power estimate from a non-precision array-current "
            "measurement; use input_power_reported for the unmodified controller value"
        )

    raw = reported_register.raw
    return (
        RegisterValue(
            name="input_power",
            address=_INPUT_POWER_ADDRESS,
            function="holding",
            raw=raw,
            value=selected,
            unit="W",
        ),
        RegisterValue(
            name="input_power_source",
            address=_INPUT_POWER_ADDRESS,
            function="holding",
            raw=raw,
            value=source,
        ),
        RegisterValue(
            name="input_power_quality",
            address=_INPUT_POWER_ADDRESS,
            function="holding",
            raw=raw,
            value=quality,
        ),
        RegisterValue(
            name="input_power_note",
            address=_INPUT_POWER_ADDRESS,
            function="holding",
            raw=raw,
            value=note,
        ),
    )
