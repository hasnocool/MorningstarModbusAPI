---
name: read-only-modbus-development
description: Safely change Morningstar Modbus transport, protocol, discovery, raw reads, polling, or connection behavior while preserving the project's strict read-only boundary and async architecture.
---

# Read-only Modbus development

Use for `transport.py`, `protocol.py`, `discovery.py`, profile polling behavior, serial/TCP connection code, or
anything that changes which Modbus exchanges are made.

## Hard boundary

The current runtime is a telemetry/identification reader, not a controller. Preserve the allowed operations:

- holding-register read (`0x03`);
- input-register read (`0x04`);
- Read Device Identification (`0x2B / 0x0E`).

Do not add write-single/multiple-register, coil write, reset/equalize/control triggers, EEPROM mutation, or a
generic raw protocol feature that makes writes possible. A vendor manual describing a writable address does not
change this contract.

## Understand the existing path first

Inspect the branch's:

- read-only client abstraction;
- RTU framing/CRC and TCP MBAP/PDU parsing;
- error/exception types;
- request timeouts and connection cleanup;
- discovery probing policy;
- exchange-observer/capture hooks;
- profile block reads and optional-block handling;
- tests for malformed/short/exception responses.

Do not create a second protocol implementation for a new feature when the existing parser/client can be reused.

## Async and serial rules

- Keep TCP I/O native-async where the current implementation does.
- PySerial is blocking; preserve the existing dedicated executor boundary instead of calling it directly from the
  event loop.
- Keep serial access serialized where required by the physical link/client.
- Bound discovery concurrency, retries, and address/network scans.
- Close streams/serial handles after failed connection attempts and when endpoints are replaced.
- Preserve cancellation; do not swallow `CancelledError` through broad exception handling.

## Discovery rules

- Prefer standard Device Identification when available.
- Use product fingerprints only when distinctive enough to avoid false classification.
- TCP discovery must remain constrained to explicit hosts or explicitly configured bounded network ranges.
- A failed optional probe should not become a device-control side effect.
- Unknown hardware should remain generic/conservative rather than guessed.

## Polling/profile reads

Catalog `RegisterBlock`s determine safe read shapes. When changing blocks or polling:

- respect holding vs input function;
- respect optional and cached metadata behavior;
- apply firmware gates before issuing reads;
- preserve full multi-word fields;
- avoid exploding one contiguous block into unnecessary requests without a reason;
- retain raw register words even if semantic decoding later fails plausibility checks.

If optimizing poll frequency or request grouping, measure the real request path and preserve protocol timing/
capacity guardrails. Do not infer safe high rates from one fast request.

## Capture compatibility

Transport exchange observers are evidence hooks. New read behavior should remain observable without changing the
request semantics. Capture should record what production transport actually did.

If request shape changes intentionally, update replay fixtures/tests that depend on strict ordering/function/
address/count.

## Tests

Cover the behavior at the narrowest useful level:

- protocol parse/frame tests for byte-level changes;
- client tests for function/address/count/error handling;
- discovery tests for identity/fingerprint and bounded scanning;
- replay tests when changing production request sequences;
- lifecycle tests for connection cleanup/recovery interactions.

Then follow `testing-and-ci`.

## Completion checks

A transport change is not done until you can explain why it remains read-only, bounded, non-blocking, cleaned up
on failure, compatible with capture/replay, and covered by deterministic tests.
