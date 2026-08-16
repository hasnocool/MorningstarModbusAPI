---
applyTo: "src/**/*.py"
---

Follow root `AGENTS.md` and the owning canonical skill. Use canonical v0.5+ package imports only.

Keep async code non-blocking, serial blocking work behind the existing executor boundary, concurrency bounded,
cleanup/cancellation correct, and shared domain logic out of FastAPI routes. Preserve immutable `controller_uid`
and raw/source provenance across layers. Use typed composable functions and configured Ruff rules.

For system/power code, model missing data explicitly; do not coerce unknown measurements to zero.
