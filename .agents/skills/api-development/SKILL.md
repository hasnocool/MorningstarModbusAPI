---
name: api-development
description: Develop read-only FastAPI controller/system endpoints, SSE streaming, history/export responses, topology/components/power views, validation, and error behavior without leaking domain logic into routes.
---

# API development

Primary ownership is `api/`, especially `api/routers/controllers.py` and `api/routers/systems.py`. Routes should
validate/present domain services; they should not own product decoding, controller identity, or power accounting.

## Current route families

Inspect the branch router/tests before relying on exact paths. The service can expose controller inventory/latest/
history/export, system/site inventory/latest/history/energy/health, topology/events/SSE, and branches containing
the component model may expose components/relationships/component graph/power flow/energy ledger.

## Rules

- Keep `/v1` compatibility where possible and document intentional migrations.
- Validate time ranges, resolution, limits, identifiers, and query parameters at the boundary.
- Preserve IDs containing `/` where supported.
- Keep product-specific register conditionals out of routes.
- Keep system metric/component/power semantics in `systems/`.
- SSE generators must be async, disconnect-aware, bounded, and heartbeat-safe.
- Stream large exports instead of building unbounded payloads.
- Use explicit HTTP status/error semantics and test them.
- Never add write-capable controller/protocol operations.

For new system endpoints, test both happy paths and missing/partial/unknown data so API presentation does not
turn absence into fabricated numeric zeroes.
