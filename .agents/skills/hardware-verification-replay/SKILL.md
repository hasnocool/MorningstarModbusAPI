---
name: hardware-verification-replay
description: Capture, replay, and verify Morningstar read behavior and evidence while keeping vendor, software, fixture, and physical-hardware verification levels distinct.
---

# Hardware verification and replay

Use `capture/` and verification tooling to validate the production read path without creating a second protocol
implementation.

## Evidence levels

Keep vendor-documented, software-tested, fixture/replay-verified, and physical-device-verified evidence separate.
A synthetic/spec-derived fixture is not physical verification.

## Rules

- Capture production read transactions and decoded/raw register evidence with source metadata.
- Replay must be strict about function/address/count/order and fail on mismatch.
- Redact structured identifiers by default; review raw frames before publication.
- Never commit secrets or unsanitized real-device evidence.
- Do not use a fixture to claim undocumented wiring, ReadyEdge reconciliation, retained-history protocol, or
  battery/load/generator measurement capability.

## System-level validation

When validating topology/component/power behavior, preserve which facts came from controller telemetry,
ReadyEdge descriptors, transport observations, or derived calculations. Physical verification can confirm a
relationship, but software should still expose confidence/provenance rather than erasing the evidence chain.
