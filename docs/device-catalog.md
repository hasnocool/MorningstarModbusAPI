# Morningstar device catalog

MorningstarModbusAPI keeps product intelligence separate from transport, persistence, API code, and verification evidence. The catalog is the checked-in, reviewable source of truth for how supported Morningstar families are read and decoded.

## Package layout

```text
src/morningstar_modbus/
├── catalog/
│   ├── __init__.py
│   ├── common.py          # shared state/fault/alarm dictionaries
│   ├── compatibility.py   # numeric firmware comparison and gates
│   ├── profile.py         # catalog-driven polling and metadata caching
│   ├── registry.py        # model selection, fingerprints, API payloads
│   ├── scaling.py         # fixed-point, Float16, BCD, ASCII, version, bitfield helpers
│   ├── types.py           # blocks, semantic registers, reserved ranges, verification dataclasses
│   ├── verification.py    # non-vendor verification evidence registry
│   └── families/          # vendor-derived product definitions
│       ├── genstar_mppt.py
│       ├── readyedge.py
│       ├── tristar_mppt.py
│       ├── tristar_mppt_600v.py
│       ├── tristar_pwm.py
│       ├── prostar_mppt.py
│       ├── prostar_pwm.py
│       ├── sunsaver_mppt.py
│       ├── sunsaver_duo.py
│       ├── suresine_classic.py
│       ├── suresine_gen2.py
│       └── relay_driver.py
├── intelligence/          # runtime identity/firmware/capability resolution
├── discovery.py           # asks catalog + resolver to identify a device
└── watcher.py             # polls the selected effective profile
```

A product family owns its read blocks, semantic register definitions, source-backed reserved ranges, scaling rules, state dictionaries, fault/alarm definitions, model aliases, communications capabilities, network defaults, stable metadata fields, firmware constraints, catalog revision, and primary Morningstar source reference.

Verification evidence does **not** live in the family module. `catalog/verification.py` records software/fixture/hardware evidence independently so a hardware observation is never presented as if it came from a Morningstar document.

## Three register concepts

The catalog deliberately distinguishes three kinds of address coverage.

### `RegisterBlock`

A contiguous read-only Modbus region the profile is allowed to read. A block can contain named fields, reserved words, and raw words retained only as evidence.

### `RegisterSpec`

A semantic single- or multi-word field. It carries the public name, starting address, word count, function, decoder, unit, category, enum/bit metadata, description, and optional firmware gates.

### `ReservedRegisterRange`

One or more words that the manufacturer explicitly documents as reserved inside an otherwise readable block. A reserved range can carry function, description, and firmware gates but intentionally has **no invented semantic register name**.

This distinction matters because broad profile reads preserve every successfully read word. A raw observation such as `holding_0x003F` can therefore exist even though `0x003F` is correctly cataloged as reserved. Raw aliases are transport/evidence identities; they are not automatically proof of a missing mapping.

A genuinely unknown/unmapped address is one that is covered by neither a semantic `RegisterSpec` nor a documented `ReservedRegisterRange`.

## Identification policy

Discovery prefers standard Modbus Read Device Identification (`0x2B / 0x0E`). Product codes are matched against ordered aliases so specific families such as TriStar MPPT 600V win before broader TriStar matches.

Some older products or bridges do not provide useful Device Identification. In those cases the registry uses a deliberately small set of read-only fingerprints only where a layout is distinctive enough to identify safely. Ambiguous layouts remain `generic`; a plausible voltage is never enough to guess a product family.

Runtime identity strength is handled by the separate intelligence resolver described in [`device-intelligence.md`](device-intelligence.md).

## Polling and metadata policy

Each profile separates ordinary runtime blocks from stable/optional metadata blocks.

- Runtime telemetry/state/fault registers refresh every poll.
- Stable metadata such as serial number, firmware, hardware revision, model flag, or Modbus identifier can be read separately and cached.
- Optional metadata failures do not automatically fail a telemetry poll.
- Every successfully read raw word is preserved alongside decoded named values.
- Firmware gates are applied before building the effective register map.
- Firmware gates can apply to read blocks, named registers, and reserved ranges independently.
- The runtime remains read-only even when vendor specifications document configurable fields.

Raw word observations use transport-oriented names such as `holding_0x0026` for evidence/capture compatibility. They are not the preferred operator-facing register identity. When the catalog documents an address, the corresponding semantic `RegisterSpec` is authoritative for decoded telemetry, unit, category, and description. When Morningstar documents the address as reserved, `ReservedRegisterRange` is authoritative and consumers should not invent a semantic name.

Frontends should prefer semantic rows, suppress raw aliases that merely overlap named multi-word fields or documented reserved ranges, and surface a raw alias as `Unmapped ...` only when the address is genuinely outside both forms of catalog coverage or when explicit raw evidence is being inspected.

## TriStar MPPT 150V v11 coverage

The TS-MPPT catalog reads two broad holding-register regions:

- runtime/status/logger block `0x0000-0x004F`;
- optional/cached factory metadata block `0xE0C0-0xE0CD`.

The v11 source explicitly marks these spans reserved:

| Range | Catalog meaning |
| --- | --- |
| `0x0005-0x0017` | reserved RAM words between scaling/firmware metadata and runtime telemetry |
| `0x002D` | reserved status word |
| `0x003F` | reserved word between MPPT sweep values and daily logger values |
| `0x004A` | reserved daily-logger word |
| `0xE0C4-0xE0CB` | reserved factory metadata words between serial number and model flag |

Those words remain available in raw block evidence but are not missing semantic definitions.

The named runtime portion from `0x0018` through `0x004F` has semantic coverage for every documented read-only field except the explicitly reserved addresses above. Multi-word hour, Ah, alarm, and counter fields are represented as one semantic value spanning their documented words.

The factory metadata area includes:

- `serial_number` at `0xE0C0` spanning four words;
- `model_flag` at `0xE0CC`;
- `hardware_version` at `0xE0CD`.

Morningstar defines the hardware revision as major version in the upper byte and minor version in the lower byte. The catalog therefore uses `byte_pair_version`; raw `0x0101` decodes as `1.1`, not decimal `257`.

## Firmware-aware catalog declarations

`RegisterBlock`, `RegisterSpec`, and `ReservedRegisterRange` can declare `since_firmware` and `until_firmware`. `DeviceProfileSpec` can declare catalog revision and a verified firmware range.

The intelligence/runtime layer uses those declarations to:

- suppress fields or reserved spans that do not apply to the connected firmware;
- surface firmware newer than the catalog's verification ceiling;
- return a device-specific effective register map through the API;
- retain the declarative family definition unchanged for review/history.

## Verification evidence

`VerificationSpec` is independent of the vendor-derived register map. The registry can report:

- `document`: whether the profile has reviewed vendor-document grounding;
- `software`: whether ordinary automated tests cover it;
- `fixture`: whether deterministic replay coverage exists and what kind;
- `hardware`: whether known physical hardware has been reviewed;
- `models`: models represented by the evidence;
- `firmware_versions`: firmware versions represented by reviewed evidence;
- `fixture_paths`: checked-in replay fixtures;
- `notes`: qualification/caveats.

At present, TriStar MPPT is the only profile with explicit non-default verification metadata: document/software evidence is `verified`, fixture evidence is `synthetic`, and hardware evidence remains `pending`. The checked-in TS-MPPT-60 firmware-29 fixture is therefore regression evidence, not physical-device verification.

## Current family coverage

| Profile | Product family | Runtime decoding | Metadata/networking |
| --- | --- | --- | --- |
| `genstar_mppt` | GenStar MPPT | Float16 telemetry, charge/load states, SOC, alarms/faults, power | firmware, serial, TCP defaults, ReadyRail context |
| `readyedge` | ReadyEdge RE-1 | DC inputs, temperatures, SOC, system faults/alarms | firmware, serial, TCP/bridge defaults |
| `tristar_mppt` | TriStar MPPT 150V | complete v11 named read-only runtime telemetry/status/counters/logger fields through `0x004F`, with source-backed reserved spans retained separately | scaling/firmware, serial, model flag, decoded hardware revision, TCP defaults |
| `tristar_mppt_600v` | TriStar MPPT 600V | firmware-aware Float16/legacy values, state/fault core | firmware, FPGA, system multiplier, TCP defaults |
| `tristar_pwm` | TriStar PWM | voltage/current/temp, mode/state, duty, alarms/faults | serial, hardware/model flag |
| `prostar_mppt` | ProStar MPPT | Float16 telemetry, charge/load states, alarms/faults, power | firmware/system voltage, Modbus/MeterBus IDs |
| `prostar_pwm` | ProStar PWM Gen3 | Float16 telemetry, charge/load states, alarms/faults | firmware/system voltage |
| `sunsaver_mppt` | SunSaver MPPT | fixed-point telemetry, charge/load states, lighting, alarms/faults | communications defaults |
| `sunsaver_duo` | SunSaver Duo | dual-battery voltage/current, duty, state, flags/faults | communications defaults |
| `suresine_classic` | SureSine Classic 300W | battery/AC telemetry, inverter state, alarms/faults | Modbus/MeterBus IDs, serial |
| `suresine_gen2` | SureSine Gen2 | DC/AC telemetry, load bits, alarms/faults, energy, relay/LED | ratings and TCP-capable model defaults |
| `relay_driver` | Relay Driver RD-1 | dedicated family selection and raw block retention | official Modbus source indexed; exact named table intentionally conservative |

Relay Driver is intentionally source-indexed rather than pretending an unverified named table is complete.

## Catalog API

`GET /v1/catalog` returns a compact list of known Morningstar families plus each profile's independent `verification` object.

`GET /v1/catalog/{profile_name}` returns the detailed declarative profile definition. The detailed payload includes read `blocks`, source-backed `reserved_ranges`, named `registers`, firmware metadata, capabilities/network defaults, and the independent verification object.

`GET /v1/devices/register-map?device_id=...` is different: it returns the effective device-specific view after applying the connected device's firmware gates. Its `blocks`, `registers`, and `reserved_ranges` contain only items applicable to that firmware.

The `morningstar-modbus verify` command also has a separate role. Its `VerificationReport` describes what one live/replayed session could read and decode; it does not currently embed the catalog verification registry.

## Source policy

Every family module points to an official Morningstar source ID recorded in `docs/vendor/morningstar/sources.json`. Register definitions and reserved classifications should be expanded from official vendor material or from captured hardware evidence whose exact identity/firmware is known and whose behavior is reconciled with vendor documentation.

Community examples are useful for tests and troubleshooting, but they are not authoritative enough to define a new register map or convert a reserved word into a named metric by themselves.

Vendor-derived family/source-index changes must satisfy the provenance gate documented in [`../catalog-proposals/README.md`](../catalog-proposals/README.md). Verification-registry changes should instead be backed by the relevant tests/fixtures or reviewed hardware evidence.
