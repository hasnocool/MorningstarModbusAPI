# Architecture

MorningstarModbusAPI is a read-only ingestion and verification boundary between physical Morningstar devices and applications that consume telemetry.

The design keeps transport, product knowledge, runtime identity, capture/replay, lifecycle management, persistence, API presentation, and vendor-source maintenance separate so each can evolve without turning the service into one controller-specific application.

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
                    watcher + device lifecycle
                    | polling / reconnect
                    | retry / backoff
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

## Capture and replay path

Transport clients accept an observer that receives completed read-only Modbus exchanges. The observer does not alter the request path; it records evidence produced by the same transport implementation used in normal operation.

```text
live transport request
        |
        +----> device
        |       |
        |       v
        |    response
        |       |
        v       v
 transport parser/validation
        |
        +----> normal caller
        |
        +----> capture observer
                  |
                  v
             bundle writer
                  |
                  v
 manifest / identity / transactions / registers / expected
                  |
                  v
             ReplayModbusClient
                  |
                  v
     normal production protocol parsers
                  |
                  v
 catalog → intelligence → validation → persistence/API tests
```

Replay is strict by design. Function code, register address, count, and transaction ordering must match the captured session. A replay fixture therefore detects accidental changes in both request shape and response interpretation.

## Capture bundle boundary

A capture bundle contains:

- `manifest.json`: capture type, endpoint metadata, profile/model/firmware context, and evidence classification;
- `identification.json`: decoded Modbus device identification;
- `transactions.jsonl`: ordered request/response records including raw frames/PDUs, request shape, timing, and errors;
- `registers.json`: raw register words and decoded named values observed during the captured poll;
- `expected.json`: assertions used by deterministic replay/integration tests.

Decoded register values are stored in `registers.json`, not duplicated into each transaction record. Structured identifiers are redacted by default. Raw protocol frames are preserved for faithful replay and can still contain identifiers, so capture review is a required publication step.

## Device lifecycle

The watcher maintains a per-device in-memory lifecycle:

```text
discovered
    ↓
connecting
    ↓
online
    ↓
degraded
    ↓
offline
    ↓
rediscovering
    ↓
online
```

Important behavior:

- a successful discovery refresh marks the device present and can update a moved endpoint;
- a device absent from the latest discovery pass is no longer polled through its stale endpoint;
- poll failures increment consecutive failure state;
- once the configured threshold is reached, the device becomes offline/rediscovering;
- failed clients are closed, forcing the next attempt to establish a fresh connection;
- retry delay grows exponentially from `retry_backoff_initial_seconds` up to `retry_backoff_max_seconds`;
- lifecycle records retain reconnect and endpoint-change counters for diagnostics.

## Maintenance sidecar

The official-source maintenance pipeline remains outside the runtime/capture path:

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
- Serial protocols use PySerial in a dedicated single-worker executor.
- Standard Modbus Device Identification is attempted when available.
- Conservative family fingerprints are used only where the map is distinctive enough to avoid guessing.
- TCP discovery is constrained to explicit hosts or explicitly configured bounded CIDRs.
- Optional exchange observers make exact capture possible without maintaining a separate protocol implementation.

### Catalog

`morningstar_modbus.catalog` is declarative product truth. Family modules define register blocks, decoders/scaling, units, states, alarm/fault bitfields, model aliases, communications capabilities, network defaults, metadata fields, firmware gates, and source IDs.

Verification evidence is kept separate from vendor-derived family definitions so fixture/hardware observations do not masquerade as vendor-source provenance.

### Intelligence

`morningstar_modbus.intelligence` resolves the connected physical device using independent evidence: Modbus identity, catalog alias selection, conservative fingerprints, targeted metadata reads, firmware compatibility, observed capabilities, and plausibility checks.

### Verification

`morningstar_modbus.verification` runs the normal resolver and profile against a live or replay client and reports model/firmware/hardware revision, transport/unit ID, intelligence status/confidence, required and optional block availability, named-register coverage, warning messages in JSON output, and the final verification outcome.

### Watcher and lifecycle

The watcher owns continuous discovery, polling, reconnect, intelligence refresh, persistence, and lifecycle transitions. It passes known firmware into profile polling so firmware-gated blocks/registers are filtered before reads/decoding.

### Storage and API

SQLite uses WAL mode and non-blocking `aiosqlite` operations. FastAPI exposes catalog definitions, device state, telemetry history, device intelligence, validation state, and effective firmware-filtered register maps. The HTTP layer does not perform controller writes.

## Read-only safety boundary

The runtime implements only the Modbus operations needed for discovery and telemetry: holding-register reads (`0x03`), input-register reads (`0x04`), and Read Device Identification (`0x2B / 0x0E`). Capture records those operations; replay reproduces them. Neither subsystem creates a write path.

Official Morningstar specifications also describe writable registers/coils. Those definitions are useful as vendor context but do not imply runtime write support.

## Failure model

- Missing optional metadata does not invalidate an otherwise successful telemetry poll.
- Unknown devices fall back to conservative generic read-only behavior rather than forced product classification.
- Implausible decoded telemetry can mark a selected intelligence profile `invalid` while preserving raw data for diagnosis.
- Firmware newer than a profile's declared verification ceiling can be surfaced as `newer-firmware-unverified` while maintaining raw read access.
- Capture/replay mismatches fail loudly instead of silently returning approximate responses.
- Device absence and repeated poll failures cause lifecycle transitions and backoff instead of endless polling against a dead endpoint.

## Extending the service

A new product family should be added by extending the catalog and tests, not by embedding product-specific conditionals in transport or API code. New vendor-derived register definitions should point to an official source ID and follow the provenance rules in `catalog-proposals/`. Fixture and hardware verification metadata should be updated separately after evidence is reviewed.
