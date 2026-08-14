# Firmware-Aware Device Intelligence

The static product catalog answers **what a Morningstar family can expose**. The
`morningstar_modbus.intelligence` package answers **what the connected physical device actually is,
which catalog rules apply to its firmware, and how strongly that conclusion is supported**.

## Package layout

```text
src/morningstar_modbus/
├── catalog/
│   ├── compatibility.py   # version comparison and firmware gates
│   ├── types.py           # declarative since/until firmware metadata
│   └── ...
└── intelligence/
    ├── __init__.py
    ├── capabilities.py    # negotiated capabilities
    ├── confidence.py      # bounded evidence score
    ├── firmware.py        # public firmware helpers
    ├── models.py          # immutable intelligence/evidence models
    ├── resolver.py        # staged identity + metadata resolution
    └── validation.py      # post-poll physical plausibility checks
```

Transport, catalog declarations, runtime intelligence, persistence, and HTTP presentation remain
separate layers.

## Resolution pipeline

1. Read standard Modbus Device Identification when available.
2. Select the most specific catalog alias.
3. Fall back to conservative read-only fingerprints only when identity is absent or incomplete.
4. Read targeted metadata fields such as firmware, serial, model flag, and hardware revision.
5. Negotiate capabilities from the catalog, active transport, and observed named registers.
6. Score independent evidence and persist the result separately from telemetry.
7. During ordinary polling, validate decoded values against broad physical plausibility envelopes.
8. Apply `since_firmware` / `until_firmware` gates to effective register blocks and named fields.

A profile with implausible decoded telemetry is marked `invalid` rather than silently persisting a
high-confidence identity. Catalogs may optionally set `firmware_verified_max`; devices newer than
that boundary are marked `newer-firmware-unverified` without preventing raw read-only access.

## Intelligence statuses

- `verified`: strong independent identity/metadata evidence and valid telemetry.
- `probable`: useful but incomplete evidence.
- `family-only`: a family was selected without enough evidence for a stronger claim.
- `newer-firmware-unverified`: device firmware is newer than the catalog's declared verification
  ceiling.
- `generic`: safe raw Modbus fallback.
- `invalid`: selected profile produced physically implausible or non-finite decoded telemetry.

## Persistence and API

Intelligence is stored in its own `device_intelligence` table so changing identity confidence does
not alter historical samples.

Useful endpoints:

```text
GET /v1/devices/intelligence?device_id=...
GET /v1/devices/profile/validation?device_id=...
GET /v1/devices/register-map?device_id=...
```

The register-map endpoint returns the effective, firmware-filtered view of the selected catalog
profile. The service remains read-only; firmware awareness changes what is read and decoded, never
what is written to a controller.
