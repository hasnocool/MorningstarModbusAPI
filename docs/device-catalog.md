# Morningstar Device Catalog

MorningstarModbusAPI keeps product intelligence separate from transport, persistence, and API code.

## Package layout

```text
src/morningstar_modbus/
├── catalog/
│   ├── __init__.py
│   ├── common.py          # shared state/fault/alarm dictionaries
│   ├── profile.py         # catalog-driven polling runtime
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
├── profiles.py            # backwards-compatible imports
├── discovery.py           # asks the catalog to identify a device
└── watcher.py             # polls the selected catalog profile
```

A product family owns its register blocks, named fields, scaling rules, state dictionaries,
fault/alarm bit definitions, model aliases, communications capabilities, network defaults,
and primary Morningstar source document.

## Identification

Discovery prefers standard Modbus Read Device Identification (`0x2B / 0x0E`). Product
codes are matched against ordered aliases so specific models such as TriStar MPPT 600V
win before broader TriStar families.

Some older products or bridges do not return useful Device Identification. In those cases
the registry uses a deliberately small set of read-only fingerprints for layouts that are
distinct enough to identify safely. Ambiguous layouts remain `generic`; the service does
not guess a product family from a plausible voltage alone.

## Polling policy

Each profile separates ordinary runtime blocks from cached metadata blocks.

- Runtime telemetry/state/fault registers are refreshed every poll.
- Stable EEPROM metadata such as serial number, hardware version, model flag, or Modbus
  identifier is read once per profile instance where the official map supports it.
- Optional metadata blocks do not make a poll fail if a firmware revision or bridge does
  not expose them.
- Every successfully read raw word is retained alongside decoded named values.
- The service remains read-only. Catalog entries may document configuration fields, but
  no Modbus write functions are added.

This keeps the catalog useful as a source of truth without turning every polling cycle into
a large EEPROM/configuration scan.

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
| `sunsaver_duo` | SunSaver Duo | dual-battery volt/current, duty, state, flags/faults | communications defaults |
| `suresine_classic` | SureSine Classic 300W | battery/AC telemetry, inverter state, alarms/faults | Modbus/MeterBus IDs, serial |
| `suresine_gen2` | SureSine Gen2 | DC/AC telemetry, load bits, alarms/faults, energy, relay/LED | ratings and TCP-capable model defaults |
| `relay_driver` | Relay Driver RD-1 | dedicated family selection and raw block retention | official MODBUS source indexed; named table intentionally pending |

`relay_driver` is intentionally marked `source-indexed` rather than pretending an
unverified register table is complete. The catalog architecture is ready for its exact
named fields once the official table is parsed and validated.

## API

`GET /v1/catalog` returns a compact list of known Morningstar families, capabilities,
coverage status, read blocks, and source references.

`GET /v1/catalog/{profile_name}` returns the detailed register definitions including
address, function, decoder/scaling rule, unit, category, enum values, and fault/alarm bits.

These endpoints describe the catalog itself; telemetry remains under `/v1/devices`.

## Source policy

Every family module points to an official Morningstar document and the same source is
recorded in `docs/vendor/morningstar/sources.json`. Register definitions should only be
expanded from a vendor document or a captured hardware fixture whose identity and firmware
are known. Community examples can be useful for testing, but are not authoritative enough
to define a new map by themselves.
