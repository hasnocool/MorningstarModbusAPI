# Architecture

MorningstarModbusAPI is a read-only ingestion boundary between physical Morningstar devices and applications that consume telemetry.

The design keeps transport, product knowledge, runtime identity, persistence, API presentation, and vendor-source maintenance separate so each can evolve without turning the service into one controller-specific application.

## Runtime data flow

```text
USB / RS-232 / RS-485                          Ethernet
          |                                       |
          v                                       v
     Modbus RTU                              Modbus TCP
          |                                       |
          +--------------- discovery -------------+
                              |
                              v
                    catalog profile selection
                              |
                              v
                  firmware-aware intelligence
                    | identity / metadata
                    | confidence / capabilities
                    | effective register map
                              |
                              v
                        watcher / polling
                              |
                    raw + decoded values
                              |
                              v
                      SQLite / WAL store
                    | telemetry history
                    | device intelligence
                              |
                              v
                         FastAPI /v1
```

## Maintenance sidecar

The official-source maintenance pipeline is intentionally outside the runtime path:

```text
docs/vendor/morningstar/sources.json
               |
               v
approved Morningstar HTTPS documents
               |
               v
maintenance download + PDF extraction
               |
               v
conservative register observations
               |
               v
advisory diff / provenance review
               |
               v
manual catalog + test change
```

The maintenance scanner does not automatically edit Python family modules and does not run inside the polling service.

## Layer responsibilities

### Transport and discovery

- TCP uses native asyncio streams.
- Serial protocols use PySerial.
- Standard Modbus Device Identification is attempted when available.
- Conservative family fingerprints are used only where the map is distinctive enough to avoid guessing.
- TCP discovery is constrained to explicit hosts or explicitly configured bounded CIDRs.

### Catalog

`morningstar_modbus.catalog` is declarative product truth. Family modules define register blocks, decoders/scaling, units, states, alarm/fault bitfields, model aliases, communications capabilities, network defaults, metadata fields, firmware gates, and source IDs.

Raw register words remain available even when a profile provides decoded values.

### Intelligence

`morningstar_modbus.intelligence` resolves the connected physical device using independent evidence: Modbus identity, catalog alias selection, conservative fingerprints, targeted metadata reads, firmware compatibility, observed capabilities, and plausibility checks.

The result is persisted separately from telemetry so identity/confidence can improve over time without rewriting historical samples.

### Watcher

The watcher owns continuous polling, reconnect, intelligence refresh, and persistence. It passes known firmware into profile polling so firmware-gated blocks/registers are filtered before reads/decoding.

### Storage

SQLite uses WAL mode and non-blocking `aiosqlite` operations. Telemetry history and device-intelligence state are separate concerns. API consumers can restart independently; retained history remains queryable after a client or dashboard disconnects.

### API

FastAPI exposes catalog definitions, device state, telemetry history, device intelligence, validation state, and effective firmware-filtered register maps. The HTTP layer does not perform controller writes.

## Concurrency model

- TCP uses asyncio-native I/O.
- PySerial is blocking, so each RTU client isolates serial operations in a dedicated single-worker executor and serializes requests with an `asyncio.Lock`.
- Serial enumeration runs through `asyncio.to_thread`.
- SQLite access uses `aiosqlite` with WAL enabled.
- Device polls can execute concurrently with `asyncio.TaskGroup`.
- TCP discovery is bounded by a semaphore.

This prevents slow serial calls, network probes, or database writes from blocking the event loop globally.

## Read-only safety boundary

The runtime implements Modbus read operations needed for discovery and telemetry: holding-register reads (`0x03`), input-register reads (`0x04`), and Read Device Identification (`0x2B / 0x0E`).

Official Morningstar specifications also describe writable registers/coils. Those definitions are useful as vendor context but do not imply runtime write support. No HTTP endpoint or normal polling path writes controller state.

## Failure model

- Missing optional metadata does not invalidate an otherwise successful telemetry poll.
- Unknown devices fall back to conservative generic read-only behavior rather than forced product classification.
- Implausible decoded telemetry can mark a selected intelligence profile `invalid` while preserving raw data for diagnosis.
- Firmware newer than a profile's declared verification ceiling can be surfaced as `newer-firmware-unverified` while maintaining raw read access.
- Reconnect/discovery is continuous; serial adapter path changes do not necessarily create a new logical device when stable USB identity exists.

## Extending the service

A new product family should be added by extending the catalog and tests, not by embedding product-specific conditionals in transport or API code. New vendor-derived register definitions should point to an official source ID and follow the provenance rules in `catalog-proposals/`.
