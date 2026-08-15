# Synthetic TriStar MPPT replay fixture

This fixture is **not** evidence from physical hardware. It is a deterministic, spec-derived transaction stream used to prove that `ReplayModbusClient` exercises the same Device Identification, metadata, firmware-aware catalog, decoding, validation, persistence, and API paths as a real capture.

Replace or supplement it with a sanitized bundle produced by `morningstar-modbus capture` from a known TS-MPPT-60 before changing the catalog's `hardware` or `fixture` verification state to `verified`.
