# GitHub Copilot instructions for MorningstarModbusAPI

Read and follow root `AGENTS.md`; it is the canonical project instruction set. Use `.agents/README.md` as the
skill index and load the relevant `.agents/skills/*/SKILL.md` procedure before substantial work.

Core project contract:

- this is a read-only Morningstar Modbus telemetry/discovery/verification service;
- do not add Modbus writes, coil writes, EEPROM/config mutation, controller reset/control, or generic
  write-capable passthrough;
- establish current branch/HEAD truth before assuming functionality, especially when another PR is open;
- product knowledge belongs in `catalog/`, runtime identity/evidence in `intelligence/`, lifecycle in
  `lifecycle.py`/`watcher.py`, persistence/history in `storage.py`/`history.py`, and HTTP presentation in
  `api.py`;
- preserve raw telemetry and evidence tiers; a synthetic replay fixture is not physical-hardware evidence;
- vendor-derived map changes require source provenance and tests; never commit full vendor PDFs;
- use async/non-blocking patterns and the existing serial executor boundary;
- add deterministic tests and run relevant tests, `ruff check .`, and `pytest -q` before claiming completion;
- update docs/config examples when public behavior changes.

Use path-specific instructions under `.github/instructions/` for Python, catalog/evidence, tests, and docs.
Specialized Copilot agents live in `.github/agents/`.
