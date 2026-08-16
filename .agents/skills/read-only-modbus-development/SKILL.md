---
name: read-only-modbus-development
description: Develop Morningstar transports, protocol, discovery, polling, and read paths while preserving the strict read-only boundary and async lifecycle semantics.
---

# Read-only Modbus development

Own changes in `transports/`, `protocol/`, `discovery/`, `polling/`, and runtime composition where appropriate.

## Hard boundary

Do not add write-register/coils, EEPROM/configuration mutation, resets, equalize/control triggers, SNMP SET, or a
generic protocol escape hatch capable of writes. Vendor write documentation is not runtime authorization.

## Workflow

1. Confirm the correct transport/function and catalog block/function type.
2. Preserve existing RTU/TCP framing, timeout, error, cancellation, and cleanup semantics.
3. Keep serial blocking I/O behind the established executor boundary; keep TCP async.
4. Use bounded discovery/poll concurrency.
5. Feed identity through `controllers/` rather than making endpoint/device IDs permanent identity.
6. Avoid putting product-specific scaling or system aggregation in transport/polling code.
7. When adding a readable range, ensure the catalog marks only source-backed safe read blocks and reserved spans.
8. Add deterministic protocol/discovery/poll tests and run `testing-and-ci`.

## Cross-layer cautions

A transport endpoint can expose multiple Modbus unit IDs and may support an inferred bridge candidate, but this
is not proof of physical electrical topology. A ReadyEdge-reported Connected Product is also not a reason to
create a new physical controller until identity evidence is reconciled.
