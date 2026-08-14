# src/morningstar_modbus/catalog/registry.py
"""Morningstar profile registry and conservative read-only device detection."""

from __future__ import annotations

import re

from morningstar_modbus.catalog.families.genstar_mppt import GENSTAR_MPPT
from morningstar_modbus.catalog.families.prostar_mppt import PROSTAR_MPPT
from morningstar_modbus.catalog.families.prostar_pwm import PROSTAR_PWM
from morningstar_modbus.catalog.families.readyedge import READYEDGE
from morningstar_modbus.catalog.families.relay_driver import RELAY_DRIVER
from morningstar_modbus.catalog.families.sunsaver_duo import SUNSAVER_DUO
from morningstar_modbus.catalog.families.sunsaver_mppt import SUNSAVER_MPPT
from morningstar_modbus.catalog.families.suresine_classic import SURESINE_CLASSIC
from morningstar_modbus.catalog.families.suresine_gen2 import SURESINE_GEN2
from morningstar_modbus.catalog.families.tristar_mppt import TRISTAR_MPPT
from morningstar_modbus.catalog.families.tristar_mppt_600v import TRISTAR_MPPT_600V
from morningstar_modbus.catalog.families.tristar_pwm import TRISTAR_PWM
from morningstar_modbus.catalog.profile import CatalogProfile
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock
from morningstar_modbus.models import DeviceIdentification
from morningstar_modbus.transport import ReadOnlyModbusClient

GENERIC = DeviceProfileSpec(
    name="generic",
    family="Generic Modbus",
    aliases=(),
    source_id="",
    source_url="",
    blocks=(RegisterBlock(0x0000, 16, optional=True),),
    registers=(),
    capabilities=("rtu", "modbus_tcp"),
    detection_priority=1000,
    coverage="raw-only",
    notes="Fallback for devices that cannot be identified safely.",
)

PROFILES: tuple[DeviceProfileSpec, ...] = tuple(
    sorted(
        (
            GENSTAR_MPPT,
            READYEDGE,
            SURESINE_GEN2,
            TRISTAR_MPPT_600V,
            TRISTAR_MPPT,
            TRISTAR_PWM,
            PROSTAR_MPPT,
            PROSTAR_PWM,
            SUNSAVER_MPPT,
            SUNSAVER_DUO,
            SURESINE_CLASSIC,
            RELAY_DRIVER,
        ),
        key=lambda item: item.detection_priority,
    )
)
PROFILE_BY_NAME = {spec.name: spec for spec in (*PROFILES, GENERIC)}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _is_explicit_non_morningstar_vendor(vendor_name: str) -> bool:
    vendor = _normalize(vendor_name)
    return bool(vendor) and "morningstar" not in vendor


def select_spec(vendor_name: str, product_code: str) -> DeviceProfileSpec:
    if _is_explicit_non_morningstar_vendor(vendor_name):
        return GENERIC
    identity = _normalize(f"{vendor_name} {product_code}")
    product = _normalize(product_code)
    for spec in PROFILES:
        for alias in sorted(spec.aliases, key=len, reverse=True):
            normalized = _normalize(alias)
            if normalized and (normalized in identity or normalized == product):
                return spec
    return GENERIC


def select_profile(vendor_name: str, product_code: str) -> CatalogProfile:
    return CatalogProfile(select_spec(vendor_name, product_code))


def get_profile(name: str) -> CatalogProfile:
    return CatalogProfile(PROFILE_BY_NAME.get(name, GENERIC))


async def detect_profile(
    client: ReadOnlyModbusClient,
    identity: DeviceIdentification,
) -> CatalogProfile:
    """Select by Device Identification, then use only conservative read-only fingerprints."""

    selected = select_profile(identity.vendor_name, identity.product_code)
    if selected.name != "generic":
        return selected

    # Never fingerprint a device that explicitly identifies as another vendor. Fingerprints are
    # reserved for Morningstar devices with incomplete identity strings and legacy devices that
    # provide no Device Identification response at all.
    if _is_explicit_non_morningstar_vendor(identity.vendor_name):
        return selected

    # SureSine Gen2 has a distinctive ratings block at 0x0003.
    try:
        words = await client.read_holding_registers(0x0003, 4)
        rated_w = words[0] * 0.1
        nominal_dc = words[1] * 0.01
        ac_rating = words[2] * 0.1
        frequency = words[3]
        if (
            100 <= rated_w <= 3000
            and 10 <= nominal_dc <= 60
            and 90 <= ac_rating <= 260
            and 45 <= frequency <= 65
        ):
            return CatalogProfile(SURESINE_GEN2)
    except Exception:
        pass

    # SureSine Classic exposes output volts/frequency as adjacent integer registers.
    try:
        volts, frequency = await client.read_holding_registers(0x000D, 2)
        if 90 <= volts <= 260 and 45 <= frequency <= 65:
            return CatalogProfile(SURESINE_CLASSIC)
    except Exception:
        pass

    # SunSaver Duo control/status lives in the otherwise unusual 0x0106 range.
    try:
        words = await client.read_holding_registers(0x0106, 6)
        if words[2] in {1, 3, 4} and words[4] <= 0x00FF:
            return CatalogProfile(SUNSAVER_DUO)
    except Exception:
        pass

    # TriStar PWM exposes control mode + state at 0x001A/0x001B.
    try:
        mode, state = await client.read_holding_registers(0x001A, 2)
        if mode in {0, 1, 2, 3} and 0 <= state <= 8:
            return CatalogProfile(TRISTAR_PWM)
    except Exception:
        pass

    return selected


def catalog_summary() -> list[dict[str, object]]:
    return [spec.to_dict(include_registers=False) for spec in PROFILES]


def catalog_detail(name: str) -> dict[str, object] | None:
    spec = PROFILE_BY_NAME.get(name)
    return spec.to_dict(include_registers=True) if spec is not None else None
