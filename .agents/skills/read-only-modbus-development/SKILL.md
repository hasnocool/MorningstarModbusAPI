---
name: read-only-modbus-development
description: Safely change Morningstar transports, protocol, discovery, raw reads, polling, or connection behavior while preserving the strict read-only boundary, immutable controller identity, and async architecture.
---

# Read-only Modbus development

Use for `transports/`, `protocol/`, `discovery/`, `polling/`, profile read behavior, serial/TCP connection code, or
anything that changes which Modbus exchanges are made.

## Hard boundary

The runtime is a telemetry/identification reader, not a controller. Preserve allowed operations already
implemented for:

- holding-register reads (`0x03`);
- input-register reads (`0x04`);
- Read Device Identification (`0x2B / 0x0E`).

Do not add write-single/multiple-register, coil writes, reset/equalize/control triggers, EEPROM/configuration
mutation, SNMP SET, or a generic raw protocol feature that makes writes possible. Vendor documentation describing
writable fields does not change this contract.

## Understand the existing path first

Inspect the branch's:

- read-only client abstraction in `transports/`;
- RTU framing/CRC and TCP MBAP/PDU codec/error handling in `protocol/`;
- request timeouts and connection cleanup;
- discovery probing policy in `discovery/`;
- exchange-observer/capture hooks;
- catalog profile block reads, optional blocks, cached metadata, and firmware gates;
- poll cadence/performance behavior in `polling/`;
- tests for malformed, short, exception, timeout, and disconnect responses.

Do not create a second protocol implementation for a new feature when the existing production parser/client can
be reused.

## Async and serial rules

- Keep TCP I/O native-async where the current implementation does.
- PySerial is blocking; preserve the established executor boundary rather than calling it on the event loop.
- Keep serial access serialized where required by the physical link/client.
- Bound discovery concurrency, retries, unit-ID scans, and network ranges.
- Close streams/serial handles after failed connection attempts and when endpoints are replaced.
- Preserve cancellation and shutdown cleanup; do not hide cancellation through broad exception handling.

## Discovery and physical identity

- Prefer standard Device Identification when available.
- Use product fingerprints only when distinctive enough to avoid false classification.
- TCP discovery must remain constrained to explicit hosts or configured bounded ranges.
- Unknown hardware stays generic/conservative rather than guessed.
- Discovery endpoints and legacy device IDs are evidence, not immutable physical identity.
- Feed observations through `controllers/` so `controller_uid` remains stable across USB/TCP endpoint changes and
  stronger identity promotion.
- A ReadyEdge descriptor or shared TCP endpoint does not by itself justify minting a duplicate physical controller.

## Polling/profile reads

Catalog `RegisterBlock`s determine safe read shapes. When changing blocks or polling:

- respect holding versus input function;
- respect optional/cached metadata behavior;
- apply firmware gates before reads;
- preserve full multi-word fields;
- preserve reserved ranges as reserved evidence;
- avoid exploding contiguous blocks into unnecessary requests without reason;
- retain raw words even if semantic decoding later fails plausibility checks.

If optimizing poll frequency or grouping, measure the real request path and preserve protocol timing/capacity
guardrails. One fast request is not proof that an aggressive sustained poll rate is safe.

## Capture compatibility

Transport exchange observers are evidence hooks. New read behavior should remain observable without changing
request semantics solely for capture. Capture records what production transport actually did.

If request shape changes intentionally, update strict replay fixtures/tests that depend on function/address/count/
order.

## Topology caution

Multiple physical controllers reachable at distinct unit IDs through one TCP endpoint can support an **inferred**
bridge candidate. Transport reachability is not proof of physical electrical wiring or power direction.

## Tests

Cover the behavior at the narrowest useful level:

- protocol parse/frame tests for byte-level changes;
- client tests for function/address/count/errors;
- discovery tests for identity/fingerprint and bounded scanning;
- controller-scope tests for identity continuity when endpoint behavior changes;
- replay tests when production request sequences change;
- lifecycle tests for cleanup/recovery interactions.

Then follow `testing-and-ci`.

## Completion checks

A transport/protocol change is not done until you can explain why it remains read-only, bounded, non-blocking,
cleaned up on failure, compatible with physical-controller identity and capture/replay, and deterministically
tested.
