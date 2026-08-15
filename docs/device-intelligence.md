# Firmware-aware device intelligence

The static catalog answers **what a Morningstar family can expose**. The `morningstar_modbus.intelligence` package answers **what the connected physical device appears to be, which catalog rules apply to its firmware, and how strongly that conclusion is supported**.

## Package layout

```text
src/morningstar_modbus/
├── catalog/
│   ├── compatibility.py   # firmware parsing/comparison and gates
│   ├── types.py           # blocks, named registers, reserved ranges, firmware metadata
│   └── ...
└── intelligence/
    ├── __init__.py
    ├── capabilities.py    # negotiated capabilities
    ├── confidence.py      # bounded evidence score
    ├── firmware.py        # public firmware helpers
    ├── models.py          # intelligence/evidence/validation models
    ├── resolver.py        # staged identity + metadata resolution + effective register map
    └── validation.py      # post-poll plausibility checks
```

Transport, catalog declarations, runtime intelligence, persistence, and HTTP presentation remain separate layers.

## Resolution pipeline

1. Attempt standard Modbus Device Identification.
2. Select the most specific catalog alias available from identity evidence.
3. Fall back to conservative read-only fingerprints only when identity is absent/incomplete and the map is distinctive enough.
4. Read targeted stable metadata such as firmware, serial number, model flag, and hardware revision.
5. Negotiate capabilities from the selected profile, active transport, and observed named registers.
6. Score independent evidence and persist the result separately from telemetry.
7. During normal polling, validate decoded values against broad physical plausibility envelopes.
8. Apply `since_firmware` / `until_firmware` gates to effective read blocks, named registers, and reserved ranges.
9. Refresh persisted intelligence as new observations improve or weaken the evidence.

## Intelligence record

The persisted record can include:

- selected catalog profile and product family;
- resolved model and serial number;
- firmware and hardware revision;
- catalog revision;
- confidence score and intelligence status;
- negotiated capabilities;
- network/transport metadata;
- structured evidence;
- validation warnings;
- additional targeted metadata.

Keeping this state separate from telemetry means a device can move from `family-only` to `probable` or `verified` as stronger evidence arrives without modifying past samples.

Metadata decoding is catalog-defined. For example, TriStar MPPT `hardware_version` at `0xE0CD` uses the `byte_pair_version` decoder because Morningstar defines major revision in the upper byte and minor revision in the lower byte. A raw value `0x0101` therefore becomes the string `1.1`, rather than decimal `257`.

## Statuses

- `verified`: strong independent identity/metadata evidence and valid telemetry.
- `probable`: useful but incomplete evidence.
- `family-only`: a family was selected without enough evidence for a stronger claim.
- `newer-firmware-unverified`: firmware is newer than the catalog's declared verification ceiling.
- `generic`: safe raw Modbus fallback with no trusted product profile.
- `invalid`: the selected profile produced implausible or non-finite decoded telemetry.

An `invalid` result does not require discarding raw Modbus data. It means the interpretation should not be trusted until the identity/profile issue is resolved.

## Plausibility validation

Validation is deliberately broad rather than pretending to diagnose the electrical system. It checks for obviously impossible/non-finite decoded values and large out-of-family ranges for categories such as voltage, current, temperature, percentage, and frequency.

The purpose is to catch a wrong profile/decoder, not to decide whether a user's solar installation is operating correctly.

## Effective register map

```text
GET /v1/devices/register-map?device_id=...
```

The effective register map is built from the persisted device-intelligence profile and firmware. It is not simply the unfiltered static catalog.

The response contains separate arrays for:

- `blocks` — read blocks applicable to the resolved firmware;
- `registers` — named semantic `RegisterSpec` fields applicable to the firmware;
- `reserved_ranges` — source-backed `ReservedRegisterRange` spans applicable to the firmware.

This separation is important. A broad block read may preserve a raw word such as `holding_0x003F`, but if that address appears in `reserved_ranges`, it is a manufacturer-reserved word rather than a missing semantic definition.

Consumers can therefore build truthful register UIs:

```text
named register       -> show semantic name/value/unit
reserved address     -> classify as reserved; do not invent a metric
unknown raw address  -> optionally show as unmapped diagnostic evidence
```

For TriStar MPPT v11, effective reserved spans currently include `0x0005-0x0017`, `0x002D`, `0x003F`, `0x004A`, and `0xE0C4-0xE0CB` when applicable to the connected firmware.

## API

```text
GET /v1/devices/intelligence?device_id=...
GET /v1/devices/profile/validation?device_id=...
GET /v1/devices/register-map?device_id=...
```

The intelligence endpoint returns persisted runtime identity/firmware/capability evidence. The validation endpoint exposes the current profile, confidence, status, evidence, and warnings. The register-map endpoint returns the firmware-filtered blocks, named registers, and documented reserved ranges for the selected catalog profile.

The family-level detailed catalog endpoint, `GET /v1/catalog/{profile_name}`, also exposes declarative `reserved_ranges`, but it is not device/firmware-specific in the same way as the effective map.

The service remains read-only: firmware intelligence changes what is read/decoded and how confidently it is interpreted; it does not write configuration or control state to the device.
