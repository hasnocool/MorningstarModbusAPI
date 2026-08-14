# src/morningstar_modbus/catalog/__init__.py
"""Morningstar product-family device intelligence catalog."""

from morningstar_modbus.catalog.profile import CatalogProfile
from morningstar_modbus.catalog.registry import (
    catalog_detail,
    catalog_summary,
    detect_profile,
    get_profile,
    select_profile,
    select_spec,
)
from morningstar_modbus.catalog.scaling import fixed_point_scale, float16, signed_16
from morningstar_modbus.catalog.types import DeviceProfileSpec, RegisterBlock, RegisterSpec

__all__ = [
    "CatalogProfile",
    "DeviceProfileSpec",
    "RegisterBlock",
    "RegisterSpec",
    "catalog_detail",
    "catalog_summary",
    "detect_profile",
    "fixed_point_scale",
    "float16",
    "get_profile",
    "select_profile",
    "select_spec",
    "signed_16",
]
