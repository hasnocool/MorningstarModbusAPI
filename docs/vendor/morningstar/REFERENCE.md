# Morningstar protocol reference notes

Verified against official Morningstar documentation indexed by this repository on **2026-08-14**. This file is an implementation aid, not a replacement for the vendor documents in `sources.json`.

## Runtime safety rule

Morningstar vendor documents commonly describe both read and write functions. MorningstarModbusAPI intentionally implements a read-only runtime boundary. Writable registers/coils may be documented as source context, but the polling service and HTTP API do not write controller configuration or control state.

## Cross-product transport baseline

Across the currently indexed product documentation, Morningstar devices use product-dependent combinations of USB, RS-232, EIA-485/RS-485, MeterBus, and Ethernet while exposing Modbus RTU and/or Modbus TCP at the application layer.

Project implications:

- **TCP:** validate MBAP transaction/protocol/unit fields and tolerate product-specific connection behavior.
- **RTU:** serialize access to each physical serial endpoint and keep blocking PySerial work off the asyncio event loop.
- **USB:** treat USB adapters/interfaces as transport to a serial Modbus protocol rather than inventing a separate application protocol.
- **EIA-485:** include unit ID in logical device identity because multiple addressed devices can share one bus.
- **Discovery:** endpoint reachability does not prove product type; prefer Device Identification and conservative product fingerprints.
- **Firmware:** use the product profile's firmware gates rather than assuming one map applies to every firmware revision.

## TriStar MPPT 150V baseline

The TriStar MPPT MODBUS Specification V11 (`MS-002582`, 2018-08-21) remains the primary source for the TriStar MPPT 150V family.

Documented baseline includes:

- Modbus RTU serial communications;
- Ethernet/Modbus TCP on supported TS-MPPT-60 variants;
- default Modbus TCP port 502 and unit ID 1;
- request-PDU register addressing;
- holding/input-register telemetry using controller-specific scaling values;
- Device Identification support and communications/network configuration context.

Useful V11 register landmarks reflected in the catalog include:

| PDU address | Meaning |
| --- | --- |
| `0x0000-0x0001` | Voltage scaling words |
| `0x0002-0x0003` | Current scaling words |
| `0x0018` | Battery voltage |
| `0x0019` | Battery terminal voltage |
| `0x001A` | Battery sense voltage |
| `0x001B` | Array voltage |
| `0x001C` | Battery charge current |
| `0x001D` | Array current |
| `0x0023` | Heatsink temperature |
| `0x0024` | Remote temperature sensor value |
| `0x0025` | Battery regulation temperature |
| `0x002C` | Fault bitfield |
| `0x002E-0x002F` | Alarm bitfield |
| `0x0032` | Charge state |
| `0x0033` | Target regulation voltage |
| `0x003A` | Output power |
| `0x003B` | Input power |
| `0x0044` | Daily charge watt-hours |

Do not extend this table by inference. New addresses/scaling rules should be checked against the appropriate official product document.

## Newer product families

The current source index includes newer specifications such as GenStar MPPT V03 and ReadyEdge V01. These products use broader metadata and telemetry maps and may expose Float16/Float32 values, SOC information, network defaults, bridging/context fields, and larger alarm/fault structures.

Do not reuse TriStar scaling on these products by analogy; each family owns its own decoders and source evidence.

## RSC-1 / EIA-485 context

Morningstar's RSC-1 documentation describes an RS-232-to-EIA-485 adapter used to connect host serial clients to a Morningstar EIA-485 network. The bus can contain multiple addressed devices, so unit ID remains part of logical identity and discovery.

## Bridged networks

Morningstar documents topologies where an Ethernet-capable Morningstar device can bridge Modbus/TCP requests to downstream devices on an EIA-485 or connected-product network. This matters for discovery because multiple logical devices can be reachable through one TCP host.

The runtime should therefore model endpoint and unit ID separately rather than treating one IP address as one controller.

## Profile-expansion checklist

For a newly supported Morningstar model/family:

1. Locate the official product/support-library entry.
2. Find the current Modbus document, register map, operation manual, or other authoritative machine-interface specification.
3. Record the source in `sources.json` and tie the family profile to its source ID.
4. Add product-specific decoding rather than borrowing scaling by assumption.
5. Declare firmware gates when a field/block is firmware-dependent.
6. Add representative tests/fixtures.
7. Preserve raw words alongside decoded values.
8. Record reviewed source SHA-256 provenance for vendor-derived catalog changes.
9. Keep runtime writes out of scope unless the project explicitly creates a separately reviewed write-safety design in the future.
