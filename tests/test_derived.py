import pytest

from morningstar_modbus.catalog.derived import derive_register_values
from morningstar_modbus.models import RegisterValue


def register(name: str, value: float, *, raw: int = 0, unit: str | None = None) -> RegisterValue:
    return RegisterValue(
        name=name,
        address=0x003B if "input_power" in name else 0x003A,
        function="holding",
        raw=(raw,),
        value=value,
        unit=unit,
    )


def by_name(values: tuple[RegisterValue, ...]) -> dict[str, RegisterValue]:
    return {value.name: value for value in values}


def test_tristar_replaces_extreme_reported_input_power_with_output_proxy() -> None:
    derived = by_name(
        derive_register_values(
            "tristar_mppt",
            (
                register("input_power_reported", 2210.45, raw=19125, unit="W"),
                register("output_power", 464.5, unit="W"),
            ),
        )
    )

    assert derived["input_power"].value == pytest.approx(464.5)
    assert derived["input_power"].unit == "W"
    assert derived["input_power"].raw == (19125,)
    assert derived["input_power_source"].value == "charge_output_proxy"
    assert derived["input_power_quality"].value == "estimated_from_output"
    assert "2210.45 W" in str(derived["input_power_note"].value)
    assert "464.50 W" in str(derived["input_power_note"].value)


def test_tristar_keeps_plausible_controller_reported_input_power() -> None:
    derived = by_name(
        derive_register_values(
            "tristar_mppt",
            (
                register("input_power_reported", 500.0, raw=4500, unit="W"),
                register("output_power", 465.0, unit="W"),
            ),
        )
    )

    assert derived["input_power"].value == pytest.approx(500.0)
    assert derived["input_power_source"].value == "controller_reported"
    assert derived["input_power_quality"].value == "reported_unverified"


def test_tristar_uses_battery_voltage_current_when_output_power_is_missing() -> None:
    derived = by_name(
        derive_register_values(
            "tristar_mppt",
            (
                register("input_power_reported", 2210.45, raw=19125, unit="W"),
                RegisterValue(
                    name="battery_voltage",
                    address=0x0018,
                    function="holding",
                    raw=(0,),
                    value=13.25,
                    unit="V",
                ),
                RegisterValue(
                    name="battery_charge_current",
                    address=0x001C,
                    function="holding",
                    raw=(0,),
                    value=35.06,
                    unit="A",
                ),
            ),
        )
    )

    assert derived["input_power"].value == pytest.approx(464.545)
    assert derived["input_power_source"].value == "charge_output_proxy"
    assert "battery_voltage_x_charge_current" in str(derived["input_power_note"].value)


def test_non_tristar_profiles_do_not_receive_tristar_derived_values() -> None:
    assert derive_register_values(
        "prostar_mppt",
        (register("input_power_reported", 500.0, unit="W"),),
    ) == ()
