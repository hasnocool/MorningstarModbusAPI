# Hardware verification and Modbus capture/replay

MorningstarModbusAPI separates vendor documentation, ordinary software tests, deterministic replay fixtures, and observations from identified physical hardware. A profile must never be marked hardware-verified solely because a PDF or synthetic fixture exists.

## Evidence levels

| Evidence | Meaning | Can establish physical-device verification? |
| --- | --- | --- |
| Vendor documented | Register behavior is grounded in an indexed Morningstar source | No |
| Software tested | Unit/integration tests exercise the implementation | No |
| Fixture verified | A committed capture bundle replays through production parsers | Not by itself |
| Physical-device verified | A reviewed capture from known model/firmware confirms the behavior | Yes |

The checked-in TriStar MPPT TS-MPPT-60 firmware-29 fixture is `synthetic-spec-derived`. It exists to exercise capture/replay semantics in CI and is intentionally **not** physical-device evidence.

Catalog verification metadata is maintained separately in `src/morningstar_modbus/catalog/verification.py`. The current TriStar MPPT entry reports document/software evidence as verified, fixture evidence as synthetic, and hardware evidence as pending.

## Capture a physical device

Capture performs read-only Device Identification, intelligence resolution, targeted metadata reads, and one firmware-aware profile poll while recording exact Modbus transport exchanges.

Serial example:

```bash
morningstar-modbus capture \
  --device /dev/ttyUSB0 \
  --transport serial \
  --unit-id 1 \
  --baudrate 9600 \
  --stop-bits 2 \
  --output captures/ts-mppt-60
```

TCP example:

```bash
morningstar-modbus capture \
  --device 192.168.1.50 \
  --transport tcp \
  --unit-id 1 \
  --tcp-port 502 \
  --output captures/ts-mppt-60-tcp
```

`--transport` can be omitted when the device string is unambiguous: `/dev/...`/`COM...` is treated as serial and other values as TCP.

### Bundle contents

```text
capture/
├── manifest.json
├── identification.json
├── transactions.jsonl
├── registers.json
└── expected.json
```

`transactions.jsonl` contains one record per transport exchange with:

- UTC timestamp;
- transport and unit ID;
- Modbus function code;
- requested address/count where applicable;
- raw request and response bytes;
- request/response PDU bytes;
- latency;
- exception/error information when an operation fails.

Decoded register values are **not** stored in each transaction record. `registers.json` stores the `RegisterValue` objects produced by the profile poll, including raw register words and decoded named values.

TCP captures preserve full request/response frames including MBAP data and PDU bytes. Successful RTU captures preserve complete request/response ADUs including CRC.

`manifest.json` records schema version, provenance, profile/family/model/firmware/hardware context, endpoint metadata, transaction count, and privacy flags. `expected.json` records replay-oriented expectations including profile, family, model, firmware, intelligence status/confidence, and the set of named registers.

## Identifier and publication safety

Structured endpoint and serial identifiers are redacted by default. Without `--include-identifiers`, the manifest target is replaced with `<redacted>`, USB serial metadata is removed, Device Identification raw objects/PDU are cleared, and named serial register values are redacted.

That structured redaction does **not** rewrite `transactions.jsonl`. Raw protocol frames can still contain serial numbers or other identifiers.

Before publishing a physical capture:

1. confirm the device model and firmware used for the recording;
2. inspect `manifest.json` and `identification.json`;
3. inspect raw transaction frames for embedded identifiers;
4. preserve enough protocol bytes for faithful replay while removing information that should not be public;
5. replay the sanitized bundle again;
6. document what was sanitized;
7. only then consider advancing hardware verification metadata.

Do not replace real evidence with invented values and then label the fixture physical-device-derived. If sanitization prevents trustworthy replay, keep the capture private and publish only non-sensitive derived expectations.

## Verify attached hardware

Human-readable report:

```bash
morningstar-modbus verify --device /dev/ttyUSB0 --transport serial
```

JSON report:

```bash
morningstar-modbus verify \
  --device 192.168.1.50 \
  --transport tcp \
  --json
```

Capture the verification exchanges at the same time:

```bash
morningstar-modbus verify \
  --device /dev/ttyUSB0 \
  --transport serial \
  --capture captures/verified-ts-mppt-60
```

`verify` uses the same identity resolver and firmware-aware profile code used by normal operation. `VerificationReport` currently includes:

- selected profile and family;
- model, firmware, and hardware revision;
- transport and unit ID;
- intelligence status and confidence;
- runtime block readable/total counts;
- metadata block readable/total counts;
- optional block readable/total counts;
- named register decoded/total counts;
- final result;
- warnings in JSON output.

The current report does **not** embed catalog revision or the independent catalog verification-evidence object. Those are available through `/v1/catalog`, `/v1/catalog/{profile_name}`, and persisted device intelligence where applicable.

The human-readable renderer focuses on identity, confidence, block/register coverage, and the final result. Use `--json` when warning messages are needed programmatically.

The command exits with status `0` for a `verified` result and `2` for a non-verified result.

## Replay in CI

```bash
morningstar-modbus replay \
  tests/fixtures/morningstar/tristar_mppt/TS-MPPT-60/synthetic-fw-29
```

JSON output:

```bash
morningstar-modbus replay \
  tests/fixtures/morningstar/tristar_mppt/TS-MPPT-60/synthetic-fw-29 \
  --json
```

`ReplayModbusClient` is strict: function code, address, count, and transaction order must match the capture. Recorded response PDUs are passed through the production protocol parsers rather than bypassing them.

The replay-driven tests can exercise:

```text
capture fixture
    ↓
ReplayModbusClient
    ↓
Device Identification
    ↓
profile detection / intelligence
    ↓
targeted metadata
    ↓
firmware-aware polling
    ↓
register decoding / validation
    ↓
SQLite persistence
    ↓
FastAPI query paths
```

## Adding the first physical TriStar fixture

Recommended workflow:

```text
1. Connect a known TS-MPPT-45 or TS-MPPT-60.
2. Record model, firmware, interface, and unit ID.
3. Run `morningstar-modbus verify --capture ...`.
4. Review/sanitize the bundle.
5. Replay the sanitized bundle locally.
6. Add explicit expected model/firmware/register assertions.
7. Add the fixture under tests/fixtures/morningstar/tristar_mppt/...
8. Run Ruff and pytest.
9. Update verification metadata only to the level justified by the evidence.
```

Keep synthetic and physical fixtures visibly distinct, for example:

```text
tests/fixtures/morningstar/
└── tristar_mppt/
    └── TS-MPPT-60/
        ├── synthetic-fw-29/
        └── fw-29-physical/
```

## Device lifecycle and reconnect verification

The watcher maintains this lifecycle **in memory**:

```text
discovered → connecting → online → degraded → offline → rediscovering → online
```

`DeviceLifecycle` tracks:

- `state`;
- `consecutive_failures`;
- `reconnect_count`;
- `endpoint_changes`;
- `last_discovered`;
- `last_success`;
- `offline_since`;
- `retry_in_seconds`;
- an internal monotonic next-retry deadline used by `can_poll()`.

Repeated failures use exponential backoff. A failed client is closed so the next eligible poll creates a fresh connection. A device absent from the latest discovery result enters `rediscovering`, its client is closed, and it is not polled until rediscovered.

```toml
[watch]
failure_threshold = 3
retry_backoff_initial_seconds = 2.0
retry_backoff_max_seconds = 60.0
```

The detailed lifecycle is **not currently persisted** to SQLite and is not exposed as a dedicated API endpoint. SQLite's `devices` table separately stores `status`, `last_seen`, and `last_error`; the storage-level status is currently `online` after discovery/successful polls and `error` after a saved poll failure.

Future hardware-in-the-loop tests should cover cable unplug/replug, USB path changes, TCP interruption, device reboot, endpoint movement, and recovery after backoff without adding any controller write operation.
