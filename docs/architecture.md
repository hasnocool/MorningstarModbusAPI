# Architecture

MorningstarModbusAPI is a read-only ingestion and verification boundary between physical Morningstar devices and applications that consume telemetry.

The design keeps transport, product knowledge, runtime identity, capture/replay, lifecycle management, persistence, API presentation, and vendor-source maintenance separate so each can evolve independently.

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
                    | simple device status
                              |
                              v
                         FastAPI /v1
```

The detailed lifecycle state machine belongs to the watcher and is currently in memory. SQLite persists telemetry, device intelligence, and a simpler `devices.status`/`last_seen`/`last_error` view.

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
     production protocol parsers
                  |
                  v
 catalog → intelligence → validation → persistence/API tests
```

Replay is strict: function code, register address, count, and transaction ordering must match the captured session.

## Capture bundle boundary

A capture bundle contains:

- `manifest.json`: schema/provenance, endpoint metadata, profile/model/firmware context, transaction count, and privacy flags;
- `identification.json`: structured Modbus Device Identification;
- `transactions.jsonl`: ordered transport records containing request/response frames and PDUs, function/address/count, latency, and errors;
- `registers.json`: raw register words and decoded named values produced by the profile poll;
- `expected.json`: replay-oriented expectations for profile/family/model/firmware/status/confidence/named registers.

Decoded register values live in `registers.json`, not in each transaction record. Structured identifiers are redacted by default, but raw protocol frames can still contain identifiers and must be reviewed before publication.

## Device lifecycle

The watcher maintains this per-device state in memory:

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

`DeviceLifecycle` tracks state, consecutive failures, reconnect count, endpoint changes, `last_discovered`, `last_success`, `offline_since`, retry delay, and an internal monotonic retry deadline.

Important behavior:

- a discovery refresh marks currently found devices present;
- endpoint changes close the existing client and increment the endpoint-change counter;
- devices absent from the newest discovery result enter `rediscovering`, have their client closed, and are excluded from polling;
- poll failures transition through `degraded` to `offline` according to `failure_threshold`;
- failed clients are closed so the next eligible attempt creates a fresh connection;
- retry delay grows exponentially from `retry_backoff_initial_seconds` to `retry_backoff_max_seconds`;
- a later successful poll resets failure/backoff state and can increment reconnect count.

The lifecycle object is not currently written to SQLite or exposed directly through FastAPI. Separately, storage marks a discovered/successfully polled device `online` and marks a saved poll failure `error`.

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

The maintenance scanner does not automatically edit family modules and does not run inside the polling service.

## Layer responsibilities

### Transport and discovery

- TCP uses native asyncio streams.
- Serial protocols use PySerial in a dedicated single-worker executor.
- Standard Modbus Device Identification is attempted when available.
- Conservative family fingerprints are used only where the map is distinctive enough to avoid guessing.
- TCP discovery is constrained to explicit hosts or explicitly configured bounded CIDRs.
- Optional exchange observers enable exact capture without a second protocol implementation.

### Catalog

`morningstar_modbus.catalog` is declarative product truth. Vendor-derived family modules define register blocks, decoders/scaling, units, states, alarm/fault bitfields, aliases, capabilities, metadata, firmware gates, and source IDs.

Independent fixture/hardware verification evidence lives in `catalog/verification.py`, outside those vendor-derived family definitions.

### Intelligence

`morningstar_modbus.intelligence` resolves the connected physical device using Device Identification, catalog aliases, conservative fingerprints, targeted metadata, firmware compatibility, observed capabilities, confidence scoring, and plausibility checks.

### Verification

`morningstar_modbus.verification` runs the normal resolver/profile against a live or replay client and returns session-level identity, firmware/hardware information, intelligence status/confidence, block availability, named-register coverage, warnings in JSON, and a final result.

This report is distinct from the catalog verification registry returned by `/v1/catalog` and `/v1/catalog/{profile_name}`.

### Watcher and lifecycle

The watcher owns continuous discovery, polling, reconnect, intelligence refresh, persistence calls, and in-memory lifecycle transitions. It passes known firmware into profile polling so firmware-gated blocks/registers are filtered before reads/decoding.

### Storage and API

SQLite uses WAL mode and non-blocking `aiosqlite` operations. It stores devices, device intelligence, poll samples, register values, and poll errors. FastAPI exposes the persisted state plus catalog/effective-register-map views; it does not currently expose the in-memory lifecycle object.

## Read-only safety boundary

The runtime implements only the Modbus operations needed for discovery and telemetry: holding-register reads (`0x03`), input-register reads (`0x04`), and Read Device Identification (`0x2B / 0x0E`). Capture records those operations; replay reproduces them. Neither subsystem creates a write path.

Official Morningstar specifications also describe writable registers/coils, but those definitions do not imply runtime write support.

## Failure model

- Missing optional metadata does not invalidate an otherwise successful telemetry poll.
- Unknown devices fall back to conservative generic read-only behavior rather than forced product classification.
- Implausible decoded telemetry can mark a selected intelligence profile `invalid` while preserving raw data.
- Firmware newer than a profile's verification ceiling can be surfaced as `newer-firmware-unverified` while maintaining raw read access.
- Capture/replay mismatches fail loudly instead of returning approximate responses.
- Device absence and repeated poll failures cause lifecycle transitions/backoff rather than endless polling against a dead endpoint.

## Extending the service

A new product family should be added by extending the catalog and tests, not by embedding product-specific conditionals in transport or API code. Vendor-derived register changes should point to official source IDs and follow `catalog-proposals/` provenance rules. Fixture/hardware verification metadata should be updated separately only when the evidence justifies it.
