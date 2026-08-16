# tests/test_profiles.py
import pytest

from morningstar_modbus.catalog.families.tristar_mppt import TRISTAR_MPPT
from morningstar_modbus.catalog.profile import CatalogProfile
from morningstar_modbus.catalog.scaling import fixed_point_scale, signed_16


def test_scaling_helpers() -> None:
    assert signed_16(0xFFFF) == -1
    assert fixed_point_scale(2, 32768) == 2.5


class FakeClient:
    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        assert address == 0
        raw = [0] * count
        raw[0] = 100
        raw[1] = 0
        raw[2] = 80
        raw[3] = 0
        raw[0x0018] = 3277
        raw[0x001B] = 6554
        raw[0x001C] = 4096
        raw[0x001D] = 2048
        raw[0x0024] = 0x0080
        raw[0x002A] = 0
        raw[0x002B] = 123
        raw[0x0031] = 6
        raw[0x0032] = 5
        raw[0x0034] = 0
        raw[0x0035] = 25
        raw[0x003A] = 1000
        raw[0x003B] = 1100
        # Morningstar reports Wh directly at 0x0044, with 10 Wh resolution.
        # A raw value of 3970 therefore means 3970 Wh, not 39,700 Wh.
        raw[0x0044] = 3970
        raw[0x0045] = 0b00101
        return raw

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        return [0] * count

    async def read_device_identification(self):
        raise NotImplementedError

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_tristar_profile_decodes_named_metrics() -> None:
    values = await CatalogProfile(TRISTAR_MPPT).poll(FakeClient())
    by_name = {item.name: item for item in values}

    assert by_name["charge_state"].value == "MPPT"
    assert by_name["led_state"].value == "GREEN"
    assert by_name["battery_voltage"].unit == "V"
    assert by_name["input_power_reported"].unit == "W"
    assert by_name["input_power"].unit == "W"
    assert by_name["input_power"].value == pytest.approx(by_name["input_power_reported"].value)
    assert by_name["input_power_source"].value == "controller_reported"
    assert by_name["operating_hours"].value == 123
    assert by_name["charge_ah_resettable"].value == 2.5
    assert by_name["daily_charge_wh"].value == 3970
    assert by_name["daily_charge_wh"].unit == "Wh"
    assert by_name["daily_flags"].value == "reset_detected,entered_float"
    assert by_name["rts_temp"].value == "DISCONNECTED"
