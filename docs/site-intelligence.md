# Site intelligence and persistent incidents

MorningstarModbusAPI keeps the observability boundary read-only while adding a proactive interpretation
layer above controller and system telemetry. The intelligence layer never writes Modbus registers, changes
charge settings, acknowledges controller alarms, or fabricates missing measurements.

## Lifecycle

`SiteIntelligenceService` evaluates only detectors for which sufficient source-backed evidence exists. Each
detector has an `evaluation_key` scoped to the system or physical `controller_uid`. Findings are reconciled
into `intelligence_incidents` in SQLite:

- a new finding opens a persistent incident;
- repeated findings update observation time and occurrence count without generating event spam;
- severity or explanation changes produce an `INCIDENT_UPDATED` lifecycle event;
- an active incident resolves only when the same evaluation key was actually evaluated and the finding is
  no longer present;
- missing measurements do not count as recovery and therefore cannot silently resolve an incident.

Lifecycle transitions are also recorded in the existing controller/system event store. System SSE exposes
those transitions as `incident_opened`, `incident_updated`, and `incident_resolved` events.

## Detectors

The initial conservative detector set covers:

- physical controller offline state;
- source-backed controller fault and alarm registers;
- battery terminal versus remote-sense voltage divergence;
- unusually low controller input/output conversion ratio when both powers are available at meaningful load;
- degraded persisted Modbus polling success or deadline behavior;
- repeated entries into Absorption over the most recent 24 hours;
- day-level telemetry evidence gaps using the controller-history reconciliation layer;
- site solar input substantially below a local time-of-day historical baseline.

Threshold findings are observations, not hardware diagnoses. Evidence attached to an incident records the
values and provenance used to reach the finding.

## Offline historical baseline

The solar-production baseline uses normalized local system history only. It compares the current site input
power with prior-day values from the same local UTC time window and reports P10, median, and P90 estimates.
A baseline remains `insufficient_evidence` until at least three comparable prior days exist. No Internet,
weather service, irradiance API, or cloud model is required.

Baseline history is aggregated inside SQLite per 15-minute bucket, controller, and register alias before the
metric's alias-priority and cross-controller semantics are applied. The work is therefore bounded by bucket
count rather than raw observation volume, so high-granularity capture never trips the per-observation
source guard that protects explicit history queries.

This intentionally makes the first intelligence release useful on isolated LAN and off-grid deployments.
Weather-aware expected production can be layered on later as additional evidence rather than replacing the
local baseline.

## Charge-cycle summary

`GET /v1/controllers/{controller_uid}/charge-cycle` collapses source-backed `charge_state` observations over
the previous 24 hours and reports transition count, Absorption entries, Float entries, the stage sequence,
and bounded time-in-state estimates. Time gaps larger than 15 minutes are not treated as continuous stage
duration.

## Health score

Health scores are intentionally decomposable rather than opaque. A site starts with five 20-point evidence
categories:

- production;
- charging;
- battery;
- communications;
- data integrity.

Active incidents apply visible severity penalties and every penalty links back to an incident UID. The score
is therefore a compact summary of current evidence, not an AI-generated diagnosis.

## API

Global and scoped incident resources:

```text
GET /v1/incidents
GET /v1/incidents/{incident_uid}
GET /v1/systems/{system_uid}/incidents
GET /v1/controllers/{controller_uid}/incidents
```

Baseline and interpretation resources:

```text
GET /v1/systems/{system_uid}/baselines
GET /v1/systems/{system_uid}/health-score
GET /v1/controllers/{controller_uid}/health-score
GET /v1/controllers/{controller_uid}/charge-cycle
```

The existing system stream additionally emits:

```text
event: incident_opened
event: incident_updated
event: incident_resolved
```

Incident evaluation is performed on incident/health reads and periodically while a system SSE stream is
active. This keeps the engine useful with the operations frontend without creating a write-capable control
surface.
