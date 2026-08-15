# Morningstar device catalog

MorningstarModbusAPI keeps product intelligence separate from transport, persistence, and API code. The catalog is the checked-in, reviewable source of truth for how supported Morningstar families are read and decoded.

## Package layout

```text
src/morningstar_modbus/
├── catalog/
│   ├── __init__.py
│   ├── common.py          # shared state/fault/alarm dictionaries
│   ├── compatibility.py   # numeric firmware comparison and gates
│   ├── profile.py         # catalog-driven polling and metadata caching
│   ├── registry.py        # model selection and conservative fingerprints
│   ├── scaling.py         # fixed-point, Float16, BCD, ASCII, bitfield helpers
│   ├── types.py           # declarative catalog dataclasses
│   └── families/
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

A product family owns its register blocks, named fields, scaling rules, state dictionaries, fault/alarm definitions, model aliases, communications capabilities, network defaults, stable metadata fields, firmware constraints, catalog revision, and primary Morningstar source reference.

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
- The runtime remains read-only even when vendor specifications document configurable fields.

## Firmware-aware catalog declarations

`RegisterBlock` and `RegisterSpec` can declare `since_firmware` and `until_firmware`. `DeviceProfileSpec` can declare catalog revision and a verified firmware range.

The intelligence/runtime layer uses those declarations to:

- suppress fields that do not exist on the connected firmware;
- surface firmware newer than the catalog's verification ceiling;
- return a device-specific effective register map through the API;
- retain the declarative family definition unchanged for review/history.

## Current family coverage

| Profile | Product family | Runtime decoding | Metadata/networking |
| --- | --- | --- | --- |
| `genstar_mppt` | GenStar MPPT | Float16 telemetry, charge/load states, SOC, alarms/faults, power | firmware, serial, TCP defaults, ReadyRail context |
| `readyedge` | ReadyEdge RE-1 | DC inputs, temperatures, SOC, system faults/alarms | firmware, serial, TCP/bridge defaults |
| `tristar_mppt` | TriStar MPPT 150V | voltage/current/power, temperatures, charge state, faults, alarms | firmware, serial, model flag, hardware, TCP defaults |
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

`GET /v1/catalog` returns a compact list of known Morningstar families, capabilities, coverage status, read blocks, source references, and catalog metadata.

`GET /v1/catalog/{profile_name}` returns the detailed declarative register definition for a profile.

`GET /v1/devices/register-map?device_id=...` returns the effective profile after applying the connected device's firmware gates.

## Source policy

Every family module points to an official Morningstar source ID recorded in `docs/vendor/morningstar/sources.json`. Register definitions should be expanded from official vendor material or from a captured hardware fixture whose exact identity/firmware is known and whose behavior is reconciled with the vendor documentation.

Community examples are useful for tests and troubleshooting, but they are not authoritative enough to define a new register map by themselves.

Catalog/source-index changes must satisfy the provenance gate documented in [`../catalog-proposals/README.md`](../catalog-proposals/README.md).
