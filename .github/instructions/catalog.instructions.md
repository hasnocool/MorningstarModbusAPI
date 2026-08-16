---
applyTo: "src/morningstar_modbus/catalog/**/*.py,src/morningstar_modbus/intelligence/**/*.py,catalog-proposals/**/*.json,docs/vendor/morningstar/**/*"
---

Load `catalog-and-intelligence` and `catalog-maintenance-provenance` from `.agents/skills/`.
Preserve source IDs, register function/word spans, decoders, units, firmware gates, reserved ranges, runtime
identity evidence, and required SHA-bound proposal/tests.

ReadyEdge Connected Product descriptors are source-backed inventory evidence; they do not automatically prove
physical identity or electrical topology. Do not invent undocumented history/event protocols or capabilities.
