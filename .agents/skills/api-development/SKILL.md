---
name: api-development
description: Add or modify read-only MorningstarModbusAPI FastAPI controller/system routes, validation, response shaping, SSE, query limits, streaming exports, component/power views, and API compatibility without leaking domain logic.
---

# API development

Use for `api/`, especially `api/app.py`, `api/routers/controllers.py`, `api/routers/systems.py`, query validation,
streaming responses, or documented `/v1` behavior.

## Establish API truth

Inspect current router/app code and API tests before relying on README endpoint tables. Active branches can add
endpoints before every summary document catches up.

Identify:

- route path/method;
- owning data/service layer;
- query/path parameters and limits;
- success shape;
- empty/not-found behavior;
- validation/error status codes;
- streaming behavior where applicable;
- backward-compatible callers/tests.

## Layer boundary

FastAPI is presentation/orchestration. Do not copy product register maps, firmware rules, scaling, discovery
fingerprints, controller identity logic, system aggregation, component reconciliation, or power formulas into
route handlers.

Routes call owning `controllers`/`history`/`systems`/catalog services and shape a stable response.

## Read-only boundary

Do not expose controller mutation through:

- write/register/coil endpoints;
- arbitrary function-code passthrough;
- admin/raw Modbus commands;
- hidden query parameters triggering reset/configuration/equalize;
- SNMP SET or generator-control convenience routes.

## Controller identifiers

Some historical device IDs contain `/` or transport delimiters. Preserve existing path-converter/query design.
Public physical-controller surfaces should use stable `controller_uid` where the current controller API does so;
preserve `source_device_id` in history evidence.

## History endpoints

When exposing telemetry history:

- normalize/validate timestamps once;
- keep half-open range semantics consistent with history helpers/tests;
- validate resolution/register-count/point limits;
- distinguish numeric versus state aggregation output;
- return useful oversized-query errors rather than consuming unbounded memory;
- use streaming responses for large exports.

## System/site endpoints

The system layer may expose inventory/latest/history/energy/health, topology, events, SSE, component graph,
components/relationships, power flow, and energy ledger depending on branch truth.

Route rules:

- system metric semantics belong in `systems/semantics.py`;
- component reconciliation/relationships belong in system services;
- power/energy derivation belongs in system power services;
- preserve complete/partial/empty quality and source observations;
- do not coerce missing measurements to zero;
- preserve observed/derived/unknown classification;
- never make charger current appear as battery net current.

## SSE

SSE generators must be async, disconnect-aware, bounded, and heartbeat-safe. Avoid blocking I/O or unbounded
per-connection state. Preserve event IDs/provenance and avoid replaying duplicates unintentionally.

## Runtime versus persisted state

Be explicit about data ownership. If detailed lifecycle is runtime-only, do not fabricate it from simpler persisted
status. If adding runtime-state APIs, define safe app ownership/reference lifetime and restart behavior.

## Compatibility

Prefer additive routes/fields. When changing an existing response:

- identify consumers/tests;
- preserve defaults when sensible;
- document breaking migration if unavoidable;
- keep OpenAPI types accurate.

## Errors and privacy

Use intentional HTTP status codes for invalid input, unknown resources, oversized queries, malformed time ranges,
and unknown system metrics. Avoid leaking local filesystem paths, secrets, or unsanitized capture identifiers.

## Tests

Use existing FastAPI/httpx patterns. Cover:

- default success;
- boundary/limit cases;
- invalid input;
- not-found/empty/partial data;
- backward compatibility;
- streaming content type/events/rows;
- special-character IDs where relevant;
- system contributor quality/provenance;
- ReadyEdge reconciliation presentation;
- observed/derived/unknown power/energy behavior.

Then follow `testing-and-ci` and update owning API docs.
