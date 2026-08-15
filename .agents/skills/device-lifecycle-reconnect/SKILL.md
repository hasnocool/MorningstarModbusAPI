---
name: device-lifecycle-reconnect
description: Fix or extend continuous discovery, USB/TCP disconnect recovery, endpoint replacement, client cleanup, retry/backoff, watcher state, and device lifecycle behavior.
---

# Device lifecycle and reconnect

Use for `lifecycle.py`, `watcher.py`, reconnect behavior, USB serial re-enumeration, TCP endpoint changes, backoff,
or stale-device handling.

Read `docs/architecture.md` and current lifecycle/watcher tests first.

## Model the lifecycle explicitly

The established in-memory lifecycle is conceptually:

```text
discovered -> connecting -> online -> degraded -> offline -> rediscovering -> online
```

Inspect the branch's actual `DeviceLifecycle` fields/transitions before changing them. Do not copy field names
from stale docs.

## Required reconnect properties

- Discovery refresh distinguishes currently present endpoints from stale ones.
- A changed endpoint closes the old client before a new one is used.
- A device absent from the newest discovery result is not continuously polled through its old endpoint.
- Poll/connection failure closes unusable clients so retries are fresh attempts.
- Repeated failures transition through degraded/offline using the configured threshold.
- Retry delay grows with bounded exponential backoff and never becomes an unbounded tight loop.
- A successful poll restores online state and resets failure/backoff state.
- Reconnect/endpoint-change counters should mean one clear thing and have deterministic tests.

For USB devices, do not rely permanently on one `/dev/ttyUSB*` path if discovery/stable identity can relocate the
same device after reconnect.

## Runtime versus persisted status

The detailed lifecycle has historically been runtime/in-memory state, while SQLite stores a simpler device
status (`online`/`error` or the current branch equivalent). Do not make API/storage claims about detailed
lifecycle persistence unless the change deliberately introduces and tests that contract.

If adding persistence:

- define authoritative ownership and restart semantics;
- decide which timestamps/counters survive process restart;
- migrate additively;
- expose API semantics explicitly;
- avoid two independent state machines.

## Concurrency

Watcher state can be touched by discovery, polling, reconnect, and shutdown paths. Preserve:

- one clear owner per mutable client/lifecycle entry;
- bounded tasks;
- lock scopes that do not wrap slow device I/O unnecessarily;
- cancellation/shutdown cleanup;
- no concurrent use of a serial transport in ways the protocol/client does not support.

## Failure behavior

Do not hide repeated errors merely to keep a device marked online. Preserve useful last-error/log evidence while
avoiding log storms. Missing optional profile registers and complete transport failure are different conditions.

## Tests

Use deterministic fake time/clients/discovery where possible. Cover:

- successful connect;
- failure threshold transitions;
- backoff growth/max/reset;
- endpoint change;
- disappearance/stale endpoint suppression;
- reconnect after reappearance;
- client close on failure/change/shutdown;
- counter/timestamp semantics.

If the request sequence changes, also consider replay tests. Finish with `testing-and-ci`.
