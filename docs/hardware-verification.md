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

A capture directory contains:

```text
capture/
├── manifest.json
├── identification.json
├── transactions.jsonl
├── registers.json
└── expected.json
```

Each transaction can preserve:

- UTC timestamp;
- transport and unit ID;
- Modbus function code;
- requested address/count where applicable;
- raw request and response bytes;
- request/response PDU bytes;
- decoded register words;
- latency;
- exception/error information when an operation fails.

TCP captures preserve the MBAP header and PDU. Successful RTU captures preserve the complete request/response ADUs including CRC.

## Identifier and publication safety

Structured endpoint and serial identifiers are redacted by default. `--include-identifiers` keeps those structured fields, but it does not change the raw frame policy.

**Raw protocol frames can contain serial numbers or other identifiers.** Before publishing a physical capture:

1. confirm the device model and firmware used for the recording;
2. inspect `manifest.json` and `identification.json`;
3. inspect raw frames for embedded identifiers;
4. keep enough protocol bytes for faithful replay while removing information that should not be public;
5. re-run replay after sanitization;
6. document what was sanitized;
7. only then consider changing hardware verification metadata.

Do not replace real evidence with invented values and then label the fixture as physical-device-derived. If sanitization prevents trustworthy replay, retain the capture privately and publish only non-sensitive derived expectations.

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

`verify` uses the same resolver/profile logic as normal operation. The report includes identity/profile selection, model/firmware/hardware revision, catalog revision, required/optional block availability, named-register coverage, plausibility validation, catalog verification evidence, and a final result.

The command returns exit status `0` for a `verified` result and `2` for a non-verified result, making it usable in scripts or hardware-in-the-loop checks.

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

This lets CI exercise:

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
9. Update verification metadata from `pending` only to the level justified by the evidence.
```

A useful naming pattern is:

```text
tests/fixtures/morningstar/
└── tristar_mppt/
    └── TS-MPPT-60/
        └── fw-29-physical/
```

Keep synthetic and physical fixtures visibly distinct.

## Device lifecycle and reconnect verification

The watcher tracks:

```text
discovered → connecting → online → degraded → offline → rediscovering → online
```

Repeated failures use exponential backoff, failed clients are closed so retries create fresh connections, and devices missing from the latest discovery pass are not polled through stale endpoints. Lifecycle records include consecutive failures, reconnect count, endpoint-change count, last successful poll, last seen time, and next retry time.

The relevant configuration is:

```toml
[watch]
failure_threshold = 3
retry_backoff_initial_seconds = 2.0
retry_backoff_max_seconds = 60.0
```

Future hardware-in-the-loop tests should cover cable unplug/replug, USB path changes, TCP interruption, device reboot, and recovery after backoff without adding any controller write operation.
