# GitHub Copilot instructions for MorningstarModbusAPI

Read and follow root `AGENTS.md`; it is canonical. Use `.agents/README.md` as the skill index and load the relevant
`.agents/skills/*/SKILL.md` before substantial work. Use the canonical `system-topology-and-power` skill for
system/site aggregation, topology, ReadyEdge component reconciliation, power-flow, or energy-ledger tasks.

Core contract:

- strictly read-only Morningstar Modbus/SNMP observability; no write/control escape hatches;
- establish branch/HEAD truth before assuming functionality;
- use canonical v0.5+ packages (`transports/`, `protocol/`, `controllers/`, `persistence/`, `history/`, `systems/`,
  `api/`, etc.), not removed flat-module ownership;
- physical identity is immutable `controller_uid`; endpoint/device aliases may change;
- preserve raw telemetry, `source_device_id`, and evidence tiers;
- systems use quality-aware normalized metrics and explicit topology confidence;
- ReadyEdge Connected Products must be reconciled to physical controllers by strong evidence before duplication;
- component/power accounting must preserve observed/derived/unknown state; never invent battery net/load/generator
  values to make the energy balance close;
- vendor-derived map changes require approved source provenance and tests; never commit full vendor PDFs;
- keep async I/O non-blocking and cleanup/retry correct;
- add deterministic tests and verify Ruff/pytest/CI before completion claims.

Use `.github/instructions/` for path-specific guidance and `.github/agents/` for specialists, including the system
specialist for topology/component/power work.
