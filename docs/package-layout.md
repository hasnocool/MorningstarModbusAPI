# Package layout

MorningstarModbusAPI uses domain-oriented packages so the filesystem mirrors the runtime architecture and Morningstar's own separation between Modbus protocol, transport/connectivity, product knowledge, controller identity, telemetry history, and application-facing APIs.

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
├── cli/                     # operator command-line entry point
│   └── main.py
├── config/                  # configuration models/loading
│   └── core.py
├── controllers/             # physical identity, inventory, scope, lifecycle
│   ├── inventory.py
│   ├── scope.py
│   └── lifecycle.py
├── discovery/               # serial/TCP endpoint discovery
│   └── service.py
├── history/                 # raw/controller-scoped query logic
│   ├── query.py
│   ├── controller_data.py
│   └── retained/            # controller-retained non-poll history sources
│       ├── service.py
│       ├── providers.py
│       ├── liveview.py
│       ├── storage.py
│       └── types.py
├── intelligence/            # runtime product identity/capability confidence
├── maintenance/             # optional vendor-source maintenance tooling
├── persistence/             # SQLite/WAL authoritative persistence
│   ├── core.py
│   └── events.py
├── polling/                 # cadence, benchmarking, performance persistence
│   ├── core.py
│   └── storage.py
├── protocol/                # read-only Modbus framing/parsing
│   └── core.py
├── runtime/                 # long-running orchestration
│   └── watcher.py
├── snmp/                    # optional inbound trap event ingestion
│   └── traps.py
├── systems/                 # multi-controller site aggregation semantics/data
│   ├── data.py
│   └── semantics.py
└── transports/              # RTU/TCP I/O and transport observers
    └── core.py
```

The existing `catalog/` and `intelligence/` packages remain the correct ownership boundaries and are not duplicated by this reorganization.

## Dependency direction

New code should prefer canonical package imports and keep dependencies flowing toward orchestration/presentation:

```text
protocol -> transports -> discovery -> intelligence/controllers -> polling
                                      |                        |
                                      v                        v
                                   history <------------- persistence
                                      |
                           systems / runtime watcher
                                      |
                                  api / cli
```

`catalog/` supplies product knowledge to discovery/intelligence/polling without depending on API or persistence presentation layers. `runtime/watcher.py` is the composition layer and may wire several domains together, but implementations should remain in their owning package.

## Canonical imports only

The project is pre-adoption, so the v0.6 development line intentionally removes the historical flat-module compatibility layer rather than carrying permanent aliases. New and existing repository code must import from the owning domain package. CI regression coverage keeps the package root thin and prevents removed flat modules from returning.

Examples:

```python
from morningstar_modbus.transports import AsyncModbusTcpClient
from morningstar_modbus.persistence import TelemetryStore
from morningstar_modbus.controllers.scope import ControllerRegistry
from morningstar_modbus.history.retained.service import ControllerHistoryService
```

There is no compatibility promise for the removed pre-release import paths.

## Retained history boundary

Controller-retained history is intentionally nested below `history/retained/`. It is not raw Modbus poll history. LiveView or future verified retained-history providers preserve explicit source/retrieval provenance and must never fabricate per-poll samples.

## Read-only invariant

The reorganization does not add Modbus write operations. Protocol and transport code remain limited to the project's established read-only operations (`0x03`, `0x04`, and `0x2B/0x0E`).
