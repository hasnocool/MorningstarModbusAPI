---
name: hardware-verification-replay
description: Work on read-only hardware capture, strict Modbus replay, verification reports, deterministic fixtures, evidence levels, and safe fixture publication.
---

# Hardware verification and replay

Use for `capture.py`, `replay.py`, `verification.py`, capture CLI flows, replay fixtures, verification registry
evidence, or end-to-end protocol regression tests.

Read `docs/hardware-verification.md` and the capture/replay source before editing.

## Evidence ladder

Keep these independently represented:

1. vendor-documented;
2. software-tested;
3. fixture-verified;
4. physical-device-verified.

Passing a unit test does not create fixture evidence. Passing a synthetic/spec-derived replay does not create
physical-hardware evidence. A physical capture must identify enough device/firmware context to justify the exact
claim being promoted.

## Capture bundle semantics

Verify the current schema on the branch. The established boundary is:

- `manifest.json` — schema/provenance/context/privacy metadata;
- `identification.json` — structured Device Identification evidence;
- `transactions.jsonl` — ordered request/response transport exchanges, frames/PDUs, shape, timing/errors;
- `registers.json` — raw words plus named/decoded profile values;
- `expected.json` — replay verification expectations.

Do not put decoded profile values into transport transactions merely for convenience.

## Privacy/sanitization

Structured serial/endpoint identifiers are redacted by default where supported. Raw Modbus frames can still
contain identifiers.

Before committing a physical capture:

- inspect manifest/identification fields;
- inspect raw frame contents where identifiers may be embedded;
- remove local paths/IPs/serials that are not needed for evidence;
- preserve enough model/firmware provenance to make the fixture meaningful;
- clearly mark synthetic vs physical source.

Never commit credentials or unrelated network/device information.

## Strict replay rules

Replay is a protocol regression surface, not a permissive mock.

- Match request order, function, address, and count.
- Decode recorded responses through production protocol parsers.
- Fail loudly on unconsumed, unexpected, or mismatched transactions.
- Do not silently substitute default values to make a test pass.
- When a legitimate production request sequence changes, regenerate/update expectations deliberately and explain
  why.

## Verification workflow

Use the same catalog/intelligence/profile pipeline for live and replay clients where practical. Verification
reports should clearly separate:

- identity/profile/family;
- model/firmware/hardware revision when known;
- transport/unit context;
- intelligence status/confidence;
- block/read availability;
- named-register coverage;
- warnings/final result.

Do not conflate a session verification report with the independent catalog verification registry returned by
catalog APIs.

## Fixture tests

A useful fixture test should exercise real production layers, not only deserialize JSON. Prefer coverage such as:

`ReplayModbusClient -> resolver -> metadata -> firmware-aware profile -> validation -> persistence/API`

Keep committed CI fixtures deterministic and independent of physical hardware/Internet.

## Physical hardware workflow

When hardware access is available, capture/verify through the read-only CLI. Review/sanitize the bundle before
publication. Only then consider advancing hardware evidence, with tests and documentation explaining exact
model/firmware scope.

## Validation

Run replay/verification tests plus affected catalog/storage/API tests, then `testing-and-ci`.
