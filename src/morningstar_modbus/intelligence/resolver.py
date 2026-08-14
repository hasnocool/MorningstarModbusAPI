# src/morningstar_modbus/intelligence/resolver.py
"""Firmware-aware device resolver layered over the static Morningstar catalog."""

from __future__ import annotations

from dataclasses import replace

from morningstar_modbus.catalog.registry import GENERIC, PROFILE_BY_NAME, detect_profile, select_spec
from morningstar_modbus.catalog.types import DeviceProfileSpec
from morningstar_modbus.intelligence.capabilities import negotiate_capabilities
from morningstar_modbus.intelligence.confidence import score
from morningstar_modbus.intelligence.firmware import compare_versions, effective_items, version_tuple
from morningstar_modbus.intelligence.models import (
    DeviceIntelligence,
    IntelligenceEvidence,
    ValidationIssue,
)
from morningstar_modbus.intelligence.validation import validate_values
from morningstar_modbus.models import DeviceIdentification, Endpoint, RegisterValue
from morningstar_modbus.transport import ReadOnlyModbusClient


def _metadata_dict(values: tuple[RegisterValue, ...]) -> dict[str, object]:
    return {
        value.name: value.value
        for value in values
        if not value.name.startswith(("holding_0x", "input_0x"))
    }


def _first(metadata: dict[str, object], *names: str) -> str:
    for name in names:
        value = metadata.get(name)
        if value not in (None, "", "NONE"):
            return str(value)
    return ""


def _status(
    spec: DeviceProfileSpec,
    confidence: float,
    firmware: str,
    warnings: tuple[ValidationIssue, ...],
) -> str:
    if spec.name == "generic":
        return "generic"
    if any(issue.severity == "error" for issue in warnings):
        return "invalid"
    if spec.firmware_verified_max and version_tuple(firmware):
        if compare_versions(firmware, spec.firmware_verified_max) > 0:
            return "newer-firmware-unverified"
    if confidence >= 0.85:
        return "verified"
    if confidence >= 0.60:
        return "probable"
    return "family-only"


async def resolve_device_intelligence(
    client: ReadOnlyModbusClient,
    identity: DeviceIdentification,
    *,
    endpoint: Endpoint | None = None,
) -> DeviceIntelligence:
    profile = await detect_profile(client, identity)
    spec = profile.spec
    evidence: list[IntelligenceEvidence] = []

    vendor = identity.vendor_name.casefold()
    if "morningstar" in vendor:
        evidence.append(IntelligenceEvidence("vendor", "Morningstar vendor identity matched", 0.28))

    selected_from_identity = select_spec(identity.vendor_name, identity.product_code)
    if selected_from_identity.name == spec.name and spec.name != "generic":
        evidence.append(IntelligenceEvidence("product-code", "product code matched catalog aliases", 0.32))
    elif spec.name != "generic":
        evidence.append(IntelligenceEvidence("fingerprint", "read-only register fingerprint matched", 0.22))

    metadata_values: tuple[RegisterValue, ...] = ()
    if spec.name != "generic":
        metadata_values = await profile.read_metadata(client)
        if metadata_values:
            evidence.append(IntelligenceEvidence("metadata", "stable metadata registers decoded", 0.18))

    metadata = _metadata_dict(metadata_values)
    firmware = (
        _first(metadata, "firmware_version", "firmware", "software_version")
        or identity.major_minor_revision
    )
    hardware = _first(metadata, "hardware_version", "hardware_revision", "fpga_version")
    model = _first(metadata, "model", "model_name", "model_flag") or identity.product_code
    serial = _first(metadata, "serial_number", "serial")

    if firmware:
        evidence.append(IntelligenceEvidence("firmware", "firmware revision resolved", 0.08))
    if serial:
        evidence.append(IntelligenceEvidence("serial", "serial number resolved", 0.06))

    confidence = score(tuple(evidence))
    warnings: list[ValidationIssue] = []
    if spec.firmware_verified_max and version_tuple(firmware):
        if compare_versions(firmware, spec.firmware_verified_max) > 0:
            warnings.append(
                ValidationIssue(
                    "newer-firmware",
                    f"device firmware {firmware} is newer than verified catalog limit "
                    f"{spec.firmware_verified_max}",
                )
            )

    return DeviceIntelligence(
        profile=spec.name,
        family=spec.family,
        model=model,
        serial_number=serial,
        firmware=firmware,
        hardware_revision=hardware,
        catalog_revision=spec.catalog_revision or spec.source_id,
        confidence=confidence,
        status=_status(spec, confidence, firmware, tuple(warnings)),
        capabilities=negotiate_capabilities(spec, endpoint=endpoint, values=metadata_values),
        network=spec.network,
        evidence=tuple(evidence),
        warnings=tuple(warnings),
        metadata=tuple(sorted(metadata.items())),
    )


def refresh_intelligence(
    intelligence: DeviceIntelligence,
    values: tuple[RegisterValue, ...],
    *,
    endpoint: Endpoint | None = None,
) -> DeviceIntelligence:
    spec = PROFILE_BY_NAME.get(intelligence.profile, GENERIC)
    validation_evidence, issues = validate_values(spec, values)
    dynamic_codes = {"named-registers", "telemetry-plausibility"}
    evidence = (
        tuple(item for item in intelligence.evidence if item.code not in dynamic_codes)
        + validation_evidence
    )
    confidence = score(evidence)
    dynamic_issue_codes = {"non-finite", "implausible-value"}
    warnings = tuple(
        item for item in intelligence.warnings if item.code not in dynamic_issue_codes
    ) + issues
    return replace(
        intelligence,
        confidence=confidence,
        status=_status(spec, confidence, intelligence.firmware, warnings),
        capabilities=negotiate_capabilities(spec, endpoint=endpoint, values=values),
        evidence=evidence,
        warnings=warnings,
    )


def effective_register_map(profile_name: str, firmware: object = "") -> dict[str, object] | None:
    spec = PROFILE_BY_NAME.get(profile_name)
    if spec is None:
        return None
    blocks = effective_items(spec.blocks, firmware)
    registers = effective_items(spec.registers, firmware)
    return {
        "profile": spec.name,
        "family": spec.family,
        "catalog_revision": spec.catalog_revision or spec.source_id,
        "firmware": str(firmware or ""),
        "blocks": [
            {
                "address": block.address,
                "count": block.count,
                "function": block.function,
                "category": block.category,
                "optional": block.optional,
                "cache": block.cache,
                "since_firmware": block.since_firmware,
                "until_firmware": block.until_firmware,
            }
            for block in blocks
        ],
        "registers": [
            {
                "name": register.name,
                "address": register.address,
                "function": register.function,
                "words": register.words,
                "decoder": register.decoder,
                "unit": register.unit,
                "category": register.category,
                "since_firmware": register.since_firmware,
                "until_firmware": register.until_firmware,
            }
            for register in registers
        ],
    }
