# tests/test_profiles.py
import pytest

from morningstar_modbus.profiles import TriStarMpptProfile, fixed_point_scale, signed_16


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
        raw[0x0032] = 5
        raw[0x003A] = 1000
        raw[0x003B] = 1100
        return raw

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        return [0] * count

    async def read_device_identification(self):
        raise NotImplementedError

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_tristar_profile_decodes_named_metrics() -> None:
    values = await TriStarMpptProfile().poll(FakeClient())
    by_name = {item.name: item for item in values}
    assert by_name["charge_state"].value == "MPPT"
    assert by_name["battery_voltage"].unit == "V"
    assert by_name["input_power"].unit == "W"
