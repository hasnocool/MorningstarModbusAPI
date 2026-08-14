# Morningstar protocol reference notes

Verified against official Morningstar documentation on **2026-08-14**. This file is a concise implementation aid, not a replacement for the vendor documents listed in `sources.json`.

## TriStar MPPT communications baseline

From the TriStar MPPT MODBUS Specification V11 (`MS-002582`, 2018-08-21):

- TriStar MPPT supports Modbus RTU over its serial communications interfaces.
- TS-MPPT-60 models also support Modbus TCP through Ethernet.
- Serial defaults are 9600 baud, 8 data bits, no parity, no flow control, with one or two stop bits accepted by the controller.
- The documented default Modbus TCP port is 502 and the default Modbus unit ID is 1.
- The controller closes the TCP socket after each Modbus response, so a fresh connection per transaction is a valid compatibility strategy.
- Register addressing in the document is expressed as request-PDU addresses.
- Core telemetry is available through holding/input-register reads and uses device-provided voltage/current scale factors.

Primary source:

- https://www.morningstarcorp.com/wp-content/uploads/technical-doc-tristar-mppt-modbus-specification-en.pdf

## Transport implications for this project

The current implementation choices should remain aligned with these vendor behaviors:

- **TCP:** serialize requests per logical client, validate MBAP transaction/protocol/unit fields, and tolerate/expect connection closure after each response.
- **RTU:** serialize access to each physical serial endpoint and keep blocking serial operations off the asyncio event loop.
- **USB:** treat USB as a host-side transport adapter to a serial protocol, not as a separate Modbus application protocol.
- **EIA-485:** expect multiple addressed devices on one physical bus; unit ID is therefore part of logical device identity.
- **Discovery:** endpoint reachability does not prove product type. Use device identification when available and retain a generic read-only fallback.

## RSC-1 / EIA-485 context

Morningstar's RSC-1 documentation describes the adapter as an RS-232-to-EIA-485 bridge operating at 9600 baud. It supports connection from a PC through RS-232, including a PC USB-to-RS-232 cable. The EIA-485 side is intended to be daisy-chained and uses differential data lines with appropriate bus wiring/termination practices.

Primary source:

- https://www.morningstarcorp.com/wp-content/uploads/operation-manual-rsc-eia-485-to-serial-en.pdf

## Cross-product connectivity context

The 2024 Morningstar Product Connectivity Manual is the main cross-product reference for adding future profiles. It separates communications interfaces from higher-level protocols and covers local and remote Modbus connections, USB/RS-232 distinctions, MeterBus networks, HTTP, SNMP, logging, security, and troubleshooting.

Primary source:

- https://www.morningstarcorp.com/wp-content/uploads/technical-doc-morningstar-product-connectivity-manual-networking-communications-en.pdf

## Bridged networks

Morningstar documents a topology where a TS-MPPT-60 can bridge Modbus/TCP requests from Ethernet onto an EIA-485 network. Multiple downstream controllers can share the EIA-485 bus as long as they have unique Modbus IDs. This is useful future context for discovery because multiple logical devices may be reachable through one TCP host.

Historical source:

- https://www.morningstarcorp.com/wp-content/uploads/2014/02/TSMPPT.REP_.485_bridging.01.EN_.pdf

## TriStar MPPT register landmarks

Useful V11 register landmarks already reflected in the current TriStar profile include:

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

Do not extend this table by inference. New addresses and scaling rules should be added only after checking the appropriate Morningstar product document.

## Product-profile expansion checklist

For each newly supported Morningstar model/family:

1. Locate the official product page and current support-library entries.
2. Find a Modbus document, register map, or other authoritative machine-interface specification.
3. Record document title, ID/version/date, URL, and verification date in `sources.json`.
4. Add a product-specific profile instead of reusing TriStar scaling by assumption.
5. Add fixtures/tests for representative raw register blocks.
6. Preserve raw words alongside decoded values.
7. Keep write support separate and explicitly guarded if it is ever introduced.
