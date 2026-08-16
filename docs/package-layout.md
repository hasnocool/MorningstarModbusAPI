# Package layout

MorningstarModbusAPI uses domain-oriented packages so the filesystem mirrors the runtime architecture and the separation between Modbus protocol, transport/connectivity, product knowledge, controller identity, telemetry history, analytics, and application-facing APIs.

## Canonical source layout

```text
src/morningstar_modbus/
├── api/                     # FastAPI app construction and resource routers
│   ├── app.py
│   └── routers/
│       ├── controllers.py
│       └── systems.py
├── capture/                 # evidence capture, strict replay, verification
│   ├── recorder.py
│   ├── replay.py
│   └── verification.py
├── catalog/                 # vendor-derived product/register truth
│   └── families/            # product profiles, including GenStar system-metering extensions
├── cli/                     # operator command-line entry point
│   └── main.py
├── config/                  # configuration models/loading
│   └── settings.py
├── controllers/             # physical identity, inventory, scope, lifecycle
│   ├── inventory.py
│   ├── scope.py
│   └── lifecycle.py
├── discovery/               # serial/TCP endpoint discovery
│   └── service.py
├── domain/                  # shared immutable models
│   └── models.py
├── history/                 # raw/controller-scoped history and v0.6 analytics
│   ├── query.py
│   ├── controller_data.py
│   ├── analytics.py         # coverage, gaps, controller energy comparison
│   └── retained/            # controller-retained non-poll history sources
│       ├── service.py
│       ├── providers.py
│       ├── liveview.py
│       ├── storage.py
│       └── types.py
├── intelligence/            # runtime product identity/capability confidence
├── maintenance/             # optional vendor-source maintenance tooling
├── persistence/             # SQLite/WAL authoritative persistence
│   ├── store.py
│   └── events.py
├── polling/                 # cadence, benchmarking, performance persistence
│   ├── service.py
│   └── storage.py
├── protocol/                # read-only Modbus framing/parsing
│   ├── codec.py
│   └── errors.py
├── runtime/                 # long-running orchestration
│   └── watcher.py
├── snmp/                    # optional inbound trap event ingestion
│   └── traps.py
├── systems/                 # multi-controller site model
│   ├── data.py              # normalized metrics/history/events/topology
│   ├── semantics.py         # cross-product metric semantics/authority
│   ├── components.py        # component graph and typed relationships
│   └── power.py             # power flow and energy ledger
└── transports/              # RTU/TCP I/O and transport observers
    └── modbus.py
```

The catalog and intelligence packages remain the ownership boundaries for vendor truth and runtime product interpretation. System semantics do not redefine vendor register facts.

## Dependency direction

New code should prefer canonical package imports and keep dependencies flowing toward orchestration/presentation:

```text
protocol -> transports -> discovery -> intelligence/controllers -> polling
                                      |                        |
                                      v                        v
                                   history <------------- persistence
                                      |
                           history analytics / systems
                                      |
                               runtime watcher
                                      |
                                  api / cli
```

`catalog/` supplies product knowledge without depending on API/persistence presentation layers. `runtime/watcher.py` is the composition layer; concrete implementations should remain in their owning packages.

## Canonical imports only

The pre-adoption flat-module compatibility layer was removed in the v0.5 line. Current v0.6 code continues to use canonical domain imports; CI should prevent removed flat modules from returning.

Examples:

```python
from morningstar_modbus.transports import AsyncModbusTcpClient
from morningstar_modbus.persistence import TelemetryStore
from morningstar_modbus.controllers.scope import ControllerRegistry
from morningstar_modbus.history.retained.service import ControllerHistoryService
from morningstar_modbus.history.analytics import ControllerHistoryAnalytics
from morningstar_modbus.systems.components import SystemComponentService
from morningstar_modbus.systems.power import SystemPowerService
```

There is no compatibility promise for removed pre-release import paths.

## History boundaries

`history/controller_data.py` is the controller-scoped read model over authoritative device-owned telemetry.

`history/retained/` owns non-poll controller evidence such as LiveView daily records. Retained providers preserve explicit source/retrieval provenance and never fabricate per-poll samples.

`history/analytics.py` is a **read-time** layer above those sources. It calculates day-level evidence coverage, gap status, bounded local energy integration, and controller-vs-local discrepancy information without mutating either source.

## Systems boundaries

`systems/data.py` owns normalized site/system read models, history, health, events, and topology.

`systems/components.py` builds evidence-aware electrical/application components and relationships.

`systems/power.py` owns power-flow and energy-ledger calculations, including conflict-aware use of source-backed whole-system measurements.

`systems/semantics.py` defines how product-specific observations map to normalized application metrics. It must preserve additive vs non-additive authority rules so already-aggregated system measurements are not double counted.

## Read-only invariant

The package organization does not add Modbus write operations. Protocol and transport code remain limited to the established read-only operations required for discovery/telemetry, and higher-level history/system services operate on observations rather than controlling devices.
