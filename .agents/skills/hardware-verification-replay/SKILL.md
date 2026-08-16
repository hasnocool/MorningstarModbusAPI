---
name: hardware-verification-replay
description: Work on read-only hardware capture, strict Modbus replay, verification reports, deterministic fixtures, controller/system evidence levels, and safe fixture publication.
---

# Hardware verification and replay

Use for `capture/`, replay clients, verification reports, capture CLI flows, fixtures, verification registry
evidence, or end-to-end protocol regression tests.

Read `docs/hardware-verification.md` and current capture/replay source before editing.

## Evidence ladder

Keep independently represented:

1. vendor-documented;
2. software-tested;
3. fixture/replay-verified;
4. physical-device-verified.

Passing a unit test does not create fixture evidence. Synthetic/spec-derived replay does not create physical
hardware evidence. Physical capture must identify enough model/firmware/context to justify the exact claim.

## Capture bundle semantics

Verify current schema. The established boundary includes:

- `manifest.json` — schema/provenance/context/privacy metadata;
- `identification.json` — structured Device Identification evidence;
- `transactions.jsonl` — ordered request/response transport exchanges;
- `registers.json` — raw words plus named/decoded profile values;
- `expected.json` — replay verification expectations.

Do not put decoded profile values into transport transactions merely for convenience.

## Privacy/sanitization

Structured serial/endpoint identifiers may be redacted, but raw Modbus frames can still contain identifiers.
Before committing a physical capture:

- inspect manifest/identification fields;
- inspect raw frames where identifiers may be embedded;
- remove unnecessary local paths/IPs/serials;
- preserve enough model/firmware provenance for meaningful evidence;
- clearly mark synthetic versus physical source.

Never commit credentials or unrelated device/network information.

## Strict replay rules

Replay is a protocol regression surface, not a permissive mock.

- Match request order, function, address, and count.
- Decode recorded responses through production protocol parsers.
- Fail loudly on unconsumed/unexpected/mismatched transactions.
- Do not silently substitute defaults to make tests pass.
- When production request sequence legitimately changes, update expectations deliberately and explain why.

## Verification workflow

Use the same catalog/intelligence/profile path for live and replay clients where practical. Reports should
separate:

- physical controller identity/profile/family;
- model/firmware/hardware revision when known;
- transport/unit context;
- intelligence confidence/status;
- block/read availability;
- named-register coverage;
- warnings/final result.

Do not conflate a session report with independent catalog verification registry state.

## Fixture tests

A useful fixture should exercise production layers, e.g. replay -> resolver -> metadata -> firmware-aware profile
-> validation -> persistence/API. Keep committed CI fixtures deterministic and independent of physical hardware or
Internet.

## System/component/power evidence

For topology or power validation, record whether facts came from:

- transport reachability;
- ReadyEdge Connected Product descriptors;
- controller telemetry;
- a software derivation;
- physical wiring/hardware inspection.

A synthetic fixture can validate reconciliation/aggregation code but cannot prove real wiring. A derived
conversion residual is not a measured load or loss. Preserve `observed`/`derived`/`unknown` classification.

## Physical hardware workflow

Capture/verify through read-only CLI paths. Review/sanitize bundles before publication. Only then consider
advancing physical-hardware evidence, with tests/docs explaining exact model/firmware scope.

## Validation

Run replay/verification tests plus affected catalog/controller/system/storage/API tests, then `testing-and-ci`.
