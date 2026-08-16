"""Source-aware component graph for Morningstar systems/sites."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass

from morningstar_modbus.catalog import get_profile
from morningstar_modbus.systems.data import SystemDataRepository

_READYEDGE_BUS_NAMES = {
    0: "meterbus_rj11_a",
    1: "meterbus_rj11_b",
    2: "rs232_a",
    3: "rs232_b",
    4: "eia485",
}

_READYEDGE_PRODUCT_PROFILES = {
    "TriStar-PWM": "tristar_pwm",
    "TriStar-MPPT": "tristar_mppt",
    "SunSaver-MPPT": "sunsaver_mppt",
    "SureSine-300": "suresine_classic",
    "TriStar-MPPT-600V": "tristar_mppt_600v",
    "ProStar-MPPT": "prostar_mppt",
    "ProStar-PWM": "prostar_pwm",
}

_CHARGE_REGISTER_NAMES = {
    "battery_charge_current",
    "charge_current",
    "output_current",
    "output_power",
    "charge_power",
    "battery_charge_power",
}


def _decoded(value: dict[str, object] | None) -> object | None:
    if value is None:
        return None
    if "value" in value:
        return value.get("value")
    if value.get("numeric_value") is not None:
        return value.get("numeric_value")
    return value.get("text_value")


def _value_map(sample: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if sample is None:
        return {}
    return {
        str(item.get("register_name")): item
        for item in sample.get("values", [])
        if isinstance(item, dict) and item.get("register_name")
    }


def _serial(value: object) -> str:
    return str(value or "").strip().strip("\x00")


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "unknown"


def _connected_uid(host_uid: str, slot: int, serial_number: str, product_type: str) -> str:
    identity = f"{host_uid}|{serial_number}|{product_type}|{slot}".encode()
    return f"cp_{hashlib.sha256(identity).hexdigest()[:20]}"


def decode_readyedge_bus_and_address(value: object) -> dict[str, object] | None:
    """Decode ReadyEdge's documented packed physical-bus / Modbus-address word."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    raw = int(value)
    bus_code = (raw >> 8) & 0xFF
    return {
        "raw": raw,
        "bus_code": bus_code,
        "bus": _READYEDGE_BUS_NAMES.get(bus_code, f"unknown_{bus_code}"),
        "modbus_id": raw & 0xFF,
    }


@dataclass(frozen=True, slots=True)
class ConnectedProductDescriptor:
    slot: int
    product_type: str
    serial_number: str
    profile: str | None
    bus: dict[str, object] | None
    status: object | None
    hardware_version: object | None
    software_version: object | None
    software_patchlevel: object | None

    def to_dict(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "product_type": self.product_type,
            "serial_number": self.serial_number,
            "profile": self.profile,
            "bus": self.bus,
            "status": self.status,
            "hardware_version": self.hardware_version,
            "software_version": self.software_version,
            "software_patchlevel": self.software_patchlevel,
        }


def readyedge_connected_products(
    sample: dict[str, object] | None,
) -> tuple[ConnectedProductDescriptor, ...]:
    """Extract documented ReadyEdge Connected Product descriptors from one sample."""
    values = _value_map(sample)
    products: list[ConnectedProductDescriptor] = []
    for slot in range(16):
        prefix = f"connected_product_{slot}_"
        product_type = _decoded(values.get(prefix + "type"))
        if product_type is None:
            continue
        product_name = str(product_type)
        if product_name.lower() in {"none", "unknown_65535"}:
            continue
        serial_number = _serial(_decoded(values.get(prefix + "serial")))
        products.append(
            ConnectedProductDescriptor(
                slot=slot,
                product_type=product_name,
                serial_number=serial_number,
                profile=_READYEDGE_PRODUCT_PROFILES.get(product_name),
                bus=decode_readyedge_bus_and_address(
                    _decoded(values.get(prefix + "bus_and_address"))
                ),
                status=_decoded(values.get(prefix + "status")),
                hardware_version=_decoded(values.get(prefix + "hardware_version")),
                software_version=_decoded(values.get(prefix + "software_version")),
                software_patchlevel=_decoded(values.get(prefix + "software_patchlevel")),
            )
        )
    return tuple(products)


class SystemComponentService:
    """Build a read-only electrical/component graph from persisted controller evidence."""

    def __init__(self, data: SystemDataRepository) -> None:
        self.data = data

    @staticmethod
    def _controller_type(profile_name: str) -> str:
        if profile_name == "readyedge":
            return "gateway"
        try:
            names = set(get_profile(profile_name).spec.register_names)
        except KeyError:
            return "controller"
        if names.intersection(_CHARGE_REGISTER_NAMES):
            return "charge_controller"
        return "controller"

    async def graph(self, identifier: str) -> dict[str, object]:
        system = await self.data.system(identifier)
        system_uid = str(system["system_uid"])
        controllers = await self.data.controllers(system_uid)
        samples = await asyncio.gather(
            *(
                self.data.controllers_data.latest(str(controller["controller_uid"]))
                for controller in controllers
            )
        )

        system_component_uid = f"system:{system_uid}"
        battery_bus_uid = f"battery_bus:{system_uid}"
        components: dict[str, dict[str, object]] = {
            system_component_uid: {
                "component_uid": system_component_uid,
                "type": "system",
                "name": system.get("name") or system_uid,
                "source": "system_membership",
                "confidence": "configured",
            },
            battery_bus_uid: {
                "component_uid": battery_bus_uid,
                "type": "battery_bus",
                "name": "logical battery bus",
                "source": "system_semantics",
                "confidence": "logical",
                "note": (
                    "Logical aggregation point for system measurements; it is not proof "
                    "of a specific physical wiring topology."
                ),
            },
        }
        relationships: list[dict[str, object]] = []
        serial_to_uid: dict[str, str] = {}
        sample_by_uid: dict[str, dict[str, object] | None] = {}

        for controller, sample in zip(controllers, samples, strict=True):
            uid = str(controller["controller_uid"])
            profile_name = str(controller.get("profile") or "")
            sample_by_uid[uid] = sample
            sample_values = _value_map(sample)
            serial_number = _serial(
                controller.get("serial_number")
                or _decoded(sample_values.get("serial_number"))
            )
            if serial_number:
                serial_to_uid[serial_number.casefold()] = uid
            components[uid] = {
                "component_uid": uid,
                "type": self._controller_type(profile_name),
                "controller_uid": uid,
                "profile": profile_name,
                "family": controller.get("family") or "",
                "model": controller.get("model") or "",
                "serial_number": serial_number,
                "firmware": controller.get("firmware") or "",
                "status": controller.get("status") or "unknown",
                "source": "physical_controller_inventory",
                "confidence": "verified",
            }
            relationships.append(
                {
                    "from": uid,
                    "to": system_component_uid,
                    "type": "member_of",
                    "confidence": "configured",
                    "source": "system_membership",
                }
            )
            if components[uid]["type"] == "charge_controller":
                relationships.append(
                    {
                        "from": uid,
                        "to": battery_bus_uid,
                        "type": "charges",
                        "confidence": "capability",
                        "source": "catalog_register_semantics",
                    }
                )

        for controller in controllers:
            host_uid = str(controller["controller_uid"])
            if str(controller.get("profile") or "") != "readyedge":
                continue
            for product in readyedge_connected_products(sample_by_uid.get(host_uid)):
                matched_uid = (
                    serial_to_uid.get(product.serial_number.casefold())
                    if product.serial_number
                    else None
                )
                target_uid = matched_uid or _connected_uid(
                    host_uid,
                    product.slot,
                    product.serial_number,
                    product.product_type,
                )
                if matched_uid is None:
                    components[target_uid] = {
                        "component_uid": target_uid,
                        "type": "connected_product",
                        "profile": product.profile,
                        "product_type": product.product_type,
                        "serial_number": product.serial_number,
                        "source": "readyedge_connected_product",
                        "confidence": "reported",
                    }
                evidence = {
                    "readyedge_controller_uid": host_uid,
                    "slot": product.slot,
                    "registers": [
                        f"connected_product_{product.slot}_type",
                        f"connected_product_{product.slot}_serial",
                        f"connected_product_{product.slot}_bus_and_address",
                    ],
                }
                relationships.append(
                    {
                        "from": host_uid,
                        "to": target_uid,
                        "type": "monitors",
                        "confidence": "verified" if matched_uid else "reported",
                        "source": "readyedge_connected_product",
                        "bus": product.bus,
                        "slot": product.slot,
                        "product_type": product.product_type,
                        "serial_number": product.serial_number,
                        "status": product.status,
                        "evidence": evidence,
                    }
                )

        return {
            "system_uid": system_uid,
            "components": list(components.values()),
            "relationships": relationships,
            "summary": {
                "component_count": len(components),
                "relationship_count": len(relationships),
                "controller_count": len(controllers),
                "readyedge_connected_products": sum(
                    1
                    for relationship in relationships
                    if relationship["source"] == "readyedge_connected_product"
                ),
            },
        }

    async def components(self, identifier: str) -> list[dict[str, object]]:
        return list((await self.graph(identifier))["components"])

    async def relationships(self, identifier: str) -> list[dict[str, object]]:
        return list((await self.graph(identifier))["relationships"])
