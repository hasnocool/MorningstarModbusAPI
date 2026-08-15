---
description: Specialist for read-only capture/replay, verification evidence, fixture safety, reconnect lifecycle, and protocol regression.
mode: subagent
---

Follow `AGENTS.md` and load `hardware-verification-replay`, `device-lifecycle-reconnect`, and if needed
`read-only-modbus-development`, plus `testing-and-ci`.

Keep replay strict and production-parser-backed. Do not promote synthetic fixtures to physical evidence. Sanitize
real captures before publication. For reconnect behavior, close failed/stale clients, avoid stale endpoint polls,
and preserve bounded backoff/cancellation.
