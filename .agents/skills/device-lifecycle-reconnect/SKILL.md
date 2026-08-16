---
name: device-lifecycle-reconnect
description: Maintain immutable physical controller identity across USB/TCP endpoint changes, reconnect, retry/backoff, presence transitions, and historical device-ID continuity.
---

# Device lifecycle and reconnect

Use for `controllers/`, `discovery/`, `runtime/`, and reconnect-sensitive transport work.

## Identity invariants

- `controller_uid` is immutable physical identity.
- Endpoint/device IDs and vendor-derived aliases can change and must not split history.
- Identity promotion retains aliases and historical `source_device_id` membership.
- Systems and component graphs reference physical controllers; they do not mint replacement identity.
- If ReadyEdge reports a product already discovered independently, reconcile by strong identity evidence rather
  than creating a duplicate physical controller.

## Lifecycle behavior

- Discovery refreshes presence/endpoints.
- Endpoint changes close stale clients before reconnect.
- Absent devices are not polled through stale endpoints.
- Failures use bounded retry/backoff and appropriate degraded/offline state.
- Successful recovery resets failure/backoff state.
- Keep in-memory lifecycle and persisted status concepts distinct unless intentionally migrating that contract.

Add regression tests for identity continuity, endpoint movement, reconnect recovery, and duplicate prevention.
