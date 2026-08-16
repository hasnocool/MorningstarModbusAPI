---
name: device-lifecycle-reconnect
description: Fix or extend continuous discovery, immutable physical controller identity, USB/TCP disconnect recovery, endpoint replacement, client cleanup, retry/backoff, watcher state, and history continuity.
---

# Device lifecycle and reconnect

Use for `controllers/`, `discovery/`, `runtime/`, reconnect behavior, USB serial re-enumeration, TCP endpoint
changes, backoff, or stale-device handling.

Read `docs/architecture.md`, controller-scope tests, and lifecycle/watcher tests first.

## Physical identity model

`controller_uid` is immutable physical-controller identity. Endpoint/device/controller aliases can change as
stronger evidence appears or hardware reconnects.

Required identity behavior:

- identity promotion retains previous aliases;
- historical device IDs remain in controller scope so history is continuous;
- a changed USB path or TCP endpoint does not automatically create a new physical controller;
- systems/component graphs reference `controller_uid`; they do not own replacement identity;
- a ReadyEdge-reported product already independently discovered should be reconciled using strong evidence such as
  serial rather than duplicated.

## Model lifecycle explicitly

The operational lifecycle is conceptually:

```text
discovered -> connecting -> online -> degraded -> offline -> rediscovering -> online
```

Inspect actual branch fields/transitions before changing them.

## Required reconnect properties

- Discovery refresh distinguishes present endpoints from stale ones.
- Changed endpoints close old clients before replacement.
- Devices absent from newest discovery are not continuously polled through stale endpoints.
- Poll/connection failure closes unusable clients so retries are fresh attempts.
- Repeated failures transition using configured thresholds.
- Retry delay uses bounded exponential backoff rather than a tight loop.
- Successful polling restores online state and resets failure/backoff state.
- Reconnect/endpoint-change counters have one clear meaning and deterministic tests.

For USB devices, never rely permanently on one `/dev/ttyUSB*` path if discovery/identity can relocate the same
physical controller.

## Runtime versus persisted state

Detailed lifecycle may be runtime/in-memory while persistence exposes simpler status. Do not claim detailed
lifecycle persistence unless the change intentionally defines it.

If adding persistence:

- define authoritative owner/restart semantics;
- decide which timestamps/counters survive restart;
- migrate additively;
- expose API semantics explicitly;
- avoid two competing state machines.

## Concurrency

Watcher state can be touched by discovery, polling, reconnect, history sync, and shutdown. Preserve:

- one clear owner per mutable client/lifecycle entry;
- bounded tasks;
- lock scopes that avoid slow device I/O;
- cancellation/shutdown cleanup;
- safe serial transport serialization.

## Failure behavior

Do not hide repeated errors merely to keep a controller online. Preserve useful last-error/event evidence while
avoiding log storms. Missing optional registers and complete transport failure are different conditions.

## Tests

Use deterministic fake time/clients/discovery where possible. Cover:

- initial identity and stronger identity promotion;
- successful connect;
- failure threshold transitions;
- backoff growth/max/reset;
- endpoint change;
- disappearance/stale endpoint suppression;
- reconnect/reappearance with same `controller_uid`;
- historical device-ID continuity;
- client close on failure/change/shutdown;
- ReadyEdge duplicate-prevention when relevant;
- counter/timestamp semantics.

If request sequence changes, consider replay tests. Finish with `testing-and-ci`.
