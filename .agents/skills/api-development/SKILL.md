---
name: api-development
description: Add or modify MorningstarModbusAPI FastAPI routes, validation, response shaping, query limits, streaming exports, and API compatibility without leaking product logic or write capabilities.
---

# API development

Use for `api.py`, FastAPI models/routes, query validation, streaming responses, or documented `/v1` behavior.

## Establish API truth

Inspect current `api.py` and API tests before relying on README endpoint tables. Active branches can add endpoints
before all summary documentation catches up.

Identify:

- route path/method;
- source of data (storage/catalog/runtime service);
- query/path parameters and limits;
- success shape;
- empty/not-found behavior;
- validation/error status codes;
- streaming behavior where applicable;
- backward-compatible callers/tests.

## Layer boundary

FastAPI is presentation/orchestration. Do not copy product register maps, firmware rules, scaling, discovery
fingerprints, or lifecycle transition logic into route handlers.

Routes should call the owning catalog/intelligence/storage/history/service layer and shape a stable response.

## Read-only boundary

Do not expose controller mutation through:

- write/register/coil endpoints;
- arbitrary function-code passthrough;
- "admin" raw Modbus commands;
- hidden query parameters that trigger resets/configuration.

This API is for discovery, evidence, telemetry, history, and diagnostics under the current project contract.

## Device identifiers

Some device IDs can contain `/` or transport-derived delimiters. Preserve the branch's path-converter/query design
rather than assuming a simple path segment. Add regression tests for identifiers that previously caused routing
bugs.

## History endpoints

When exposing telemetry history:

- normalize/validate timestamps once;
- keep half-open range semantics consistent with `history.py`;
- validate resolution/register-count/point limits;
- distinguish numeric vs state aggregation output;
- return guidance for oversized normal JSON requests rather than consuming unbounded memory;
- use streaming responses for large exports.

## Runtime versus persisted state

Be explicit about where data comes from. If detailed lifecycle exists only in watcher memory, do not fabricate it
from a simpler persisted `devices.status`. If a task adds runtime-state APIs, define how the FastAPI app obtains a
safe live reference and what happens before watcher startup/restart.

## Compatibility

Prefer additive routes/fields. If changing an existing response:

- identify consumers/tests;
- preserve old query defaults when sensible;
- document breaking changes/migration if unavoidable;
- keep OpenAPI types accurate.

## Errors

Use intentional HTTP status codes for invalid input, unknown resources, oversized queries, and malformed time
ranges. Do not convert every internal error into HTTP 200 with an `error` string.

Avoid leaking local filesystem paths, raw secrets, or unsanitized capture identifiers in errors.

## Tests

Use FastAPI/httpx test patterns already in the repo. Cover:

- default success;
- boundary/limit cases;
- invalid input;
- not-found/empty data;
- backward compatibility;
- streaming content type/rows when relevant;
- device IDs with special path characters where relevant.

Then follow `testing-and-ci` and update API docs.
