"""Read-only Modbus capture bundles for hardware evidence and replay."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from morningstar_modbus.domain.models import DeviceIdentification, Endpoint, ModbusExchange, RegisterValue
from morningstar_modbus.intelligence.models import DeviceIntelligence

CAPTURE_SCHEMA_VERSION = 1


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class CaptureRecorder:
    """Thread-safe in-memory observer used by TCP and RTU transports."""

    def __init__(self) -> None:
        self._items: list[ModbusExchange] = []
        self._lock = threading.Lock()

    def record(self, exchange: ModbusExchange) -> None:
        with self._lock:
            self._items.append(exchange)

    @property
    def exchanges(self) -> tuple[ModbusExchange, ...]:
        with self._lock:
            return tuple(self._items)


def _structured_identification(
    identification: DeviceIdentification,
    *,
    include_identifiers: bool,
) -> dict[str, object]:
    payload = identification.to_dict()
    if not include_identifiers:
        payload["raw_objects"] = []
        payload["raw_pdu_hex"] = ""
    return payload


def _register_payload(
    values: tuple[RegisterValue, ...],
    *,
    include_identifiers: bool,
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for value in values:
        item = value.to_dict()
        if not include_identifiers and value.name in {"serial", "serial_number"}:
            item["value"] = "<redacted>"
        payload.append(item)
    return payload


def write_capture_bundle(
    destination: str | Path,
    *,
    endpoint: Endpoint,
    identification: DeviceIdentification,
    intelligence: DeviceIntelligence,
    values: tuple[RegisterValue, ...],
    exchanges: tuple[ModbusExchange, ...],
    include_identifiers: bool = False,
    provenance: str = "physical-device-capture",
) -> Path:
    """Write a directory-shaped capture bundle with exact raw exchanges."""

    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    endpoint_payload = asdict(endpoint)
    if not include_identifiers:
        endpoint_payload["target"] = "<redacted>"
        endpoint_payload["usb_serial"] = None

    manifest = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "created_at": _utcnow(),
        "provenance": provenance,
        "profile": intelligence.profile,
        "family": intelligence.family,
        "model": intelligence.model,
        "firmware": intelligence.firmware,
        "hardware_revision": intelligence.hardware_revision,
        "endpoint": endpoint_payload,
        "transaction_count": len(exchanges),
        "privacy": {
            "structured_identifiers_included": include_identifiers,
            "raw_transactions_may_contain_device_identifiers": True,
        },
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / "identification.json").write_text(
        json.dumps(
            _structured_identification(identification, include_identifiers=include_identifiers),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with (root / "transactions.jsonl").open("w", encoding="utf-8") as handle:
        for exchange in exchanges:
            handle.write(json.dumps(exchange.to_dict(), sort_keys=True) + "\n")
    (root / "registers.json").write_text(
        json.dumps(
            _register_payload(values, include_identifiers=include_identifiers),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    expected = {
        "profile": intelligence.profile,
        "family": intelligence.family,
        "model": intelligence.model,
        "firmware": intelligence.firmware,
        "status": intelligence.status,
        "confidence": intelligence.confidence,
        "named_registers": sorted(
            value.name
            for value in values
            if not value.name.startswith(("holding_0x", "input_0x"))
        ),
    }
    (root / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root


def load_capture_transactions(bundle: str | Path) -> tuple[dict[str, object], ...]:
    path = Path(bundle) / "transactions.jsonl"
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def load_capture_manifest(bundle: str | Path) -> dict[str, object]:
    return json.loads((Path(bundle) / "manifest.json").read_text(encoding="utf-8"))
