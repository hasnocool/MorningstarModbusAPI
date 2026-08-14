# Morningstar vendor documentation

This directory is the canonical reference index for official Morningstar documentation used by MorningstarModbusAPI.

The source catalog was verified against Morningstar's public product/support pages on **2026-08-14**. Full vendor PDFs are intentionally not committed to this repository. Instead, `sources.json` records the official URLs and `tools/fetch_morningstar_docs.py` can download current copies into an ignored local cache when needed for development, testing, or agent context.

## Fetch the official documents locally

```bash
python tools/fetch_morningstar_docs.py
```

The default destination is:

```text
docs/vendor/morningstar/cache/
```

That directory is git-ignored. To inspect the catalog without downloading anything:

```bash
python tools/fetch_morningstar_docs.py --list
```

To refresh existing cached copies:

```bash
python tools/fetch_morningstar_docs.py --refresh
```

To fetch one source only:

```bash
python tools/fetch_morningstar_docs.py --source tristar-mppt-modbus-v11
```

## Primary references

| Reference | Why it matters |
| --- | --- |
| [TriStar MPPT MODBUS Specification V11](https://www.morningstarcorp.com/wp-content/uploads/technical-doc-tristar-mppt-modbus-specification-en.pdf) | Authoritative TriStar MPPT Modbus RTU/TCP transport parameters, register maps, scaling, network registers, EEPROM fields, coils, alarms, faults, and protocol behavior. |
| [Morningstar Product Connectivity Manual](https://www.morningstarcorp.com/wp-content/uploads/technical-doc-morningstar-product-connectivity-manual-networking-communications-en.pdf) | Cross-product communications reference for RS-232, USB, MeterBus, Modbus networks, local/remote connectivity, HTTP, SNMP, logging, security, and troubleshooting. |
| [RSC-1 RS-232 / EIA-485 Manual](https://www.morningstarcorp.com/wp-content/uploads/operation-manual-rsc-eia-485-to-serial-en.pdf) | Wiring and serial characteristics for Morningstar's RS-232-to-EIA-485 adapter and USB-to-RS-232 host connections. |
| [TriStar MPPT Operation Manual](https://www.morningstarcorp.com/wp-content/uploads/operation-manual-tristar-mppt-en.pdf) | Controller behavior, diagnostics, alarms/faults, and communication chapters covering MeterBus, RS-232, EIA-485, and Ethernet. |

## Secondary references

| Reference | Why it matters |
| --- | --- |
| [TriStar MPPT Networking Companion](https://www.morningstarcorp.com/wp-content/uploads/technical-doc-tristar-mppt-networking-companion-document-en.pdf) | Older but useful DHCP/LAN and remote-access background for Ethernet-enabled TriStar MPPT controllers. |
| [TriStar MPPT Meter Map](https://www.morningstarcorp.com/meter-map-tristar-mppt-en/) | Human-facing labels for telemetry, operating state, diagnostics, alarms, faults, counters, and logged values. |
| [TriStar MPPT EIA-485 / Modbus-TCP Bridging](https://www.morningstarcorp.com/wp-content/uploads/2014/02/TSMPPT.REP_.485_bridging.01.EN_.pdf) | Reference architecture for a TS-MPPT-60 bridging Modbus/TCP requests to multiple devices on an EIA-485 bus. |
| [TriStar MPPT product page](https://www.morningstarcorp.com/products/tristar-mppt/) | Canonical landing page for current manuals, firmware, meter map, Modbus documentation, and support files. |
| [Morningstar support library](https://www.morningstarcorp.com/support/library/) | Starting point for additional product-specific register maps, meter maps, operation manuals, and connectivity documents as more device profiles are added. |

## How this should be used

When implementing or reviewing a Morningstar device profile:

1. Start with `sources.json` and the official product page.
2. Prefer the product's Modbus specification/register map over inferred addresses.
3. Preserve raw register values even when decoded fields are available.
4. Keep transport rules separate from product-specific scaling and interpretation.
5. Treat older networking/bridging documents as historical context when a newer connectivity document conflicts with them.
6. Record the exact source document/version used when adding new register definitions.

See [REFERENCE.md](REFERENCE.md) for the concise protocol facts currently relevant to this codebase.
