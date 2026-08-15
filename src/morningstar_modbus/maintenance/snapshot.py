# src/morningstar_modbus/maintenance/snapshot.py
"""Deterministic snapshots of the checked-in Morningstar catalog."""

from __future__ import annotations

from morningstar_modbus.catalog.registry import PROFILES


def catalog_source_ids() -> set[str]:
    return {profile.source_id for profile in PROFILES if profile.source_id}


def catalog_snapshot() -> dict[str, object]:
    profiles: list[dict[str, object]] = []
    for profile in sorted(PROFILES, key=lambda item: item.name):
        profiles.append(
            {
                "name": profile.name,
                "family": profile.family,
                "source_id": profile.source_id,
                "source_url": profile.source_url,
                "catalog_revision": profile.catalog_revision,
                "firmware_verified_min": profile.firmware_verified_min,
                "firmware_verified_max": profile.firmware_verified_max,
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
                    for register in sorted(
                        profile.registers,
                        key=lambda item: (item.function, item.address, item.name),
                    )
                ],
            }
        )
    return {"profiles": profiles}
