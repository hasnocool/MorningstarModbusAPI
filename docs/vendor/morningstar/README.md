# Morningstar vendor documentation

This directory is the canonical reference index for official Morningstar documentation used by MorningstarModbusAPI.

The machine-readable catalog is [`sources.json`](sources.json). It records source IDs, document titles/versions where known, official Morningstar URLs, repository-facing filenames, priority, and why each source matters.

## Repository policy

Complete Morningstar vendor PDFs are not republished in this repository. They remain available from Morningstar's official site and are downloaded on demand by the maintenance tooling into a git-ignored cache.

This keeps the project reviewable while still allowing every catalog decision to be tied to an exact source artifact and SHA-256 digest.

The human-readable PDF manifest is [`pdfs/README.md`](pdfs/README.md).

## Obtain the official documents

Install the optional maintenance dependency:

```bash
python -m pip install -e '.[maintenance]'
```

Download the active official source set and generate an advisory report:

```bash
python -m morningstar_modbus.maintenance scan
```

Default cache:

```text
docs/vendor/morningstar/cache/
```

Reuse existing cached files instead of refreshing them:

```bash
python -m morningstar_modbus.maintenance scan --use-cache
```

Use a different local cache when desired:

```bash
python -m morningstar_modbus.maintenance scan \
  --cache-dir /tmp/morningstar-docs \
  --output-dir /tmp/morningstar-report
```

To validate the source index without network/PDF extraction:

```bash
python -m morningstar_modbus.maintenance validate
```

## Primary references

The catalog currently references official Modbus specifications for GenStar MPPT, ReadyEdge, TriStar MPPT 150V/600V, TriStar PWM, ProStar MPPT/PWM, SunSaver MPPT/Duo, SureSine Classic/Gen2, and Relay Driver, plus cross-product connectivity/operation references.

Use [`sources.json`](sources.json) rather than copying URLs into code. It is the canonical mapping between a family module and its vendor evidence.

## How sources should be used

When implementing or reviewing a Morningstar device profile:

1. Start with the profile's `source_id` and `sources.json` entry.
2. Prefer the product's official Modbus specification/register map over inferred addresses.
3. Preserve raw register values even when decoded fields are available.
4. Keep transport behavior separate from product-specific scaling and interpretation.
5. Treat older networking/bridging material as historical context when newer official documentation supersedes it.
6. Record the exact source artifact SHA-256 in a catalog-proposal provenance record when changing vendor-derived register definitions.
7. Add or change tests together with catalog/source-index changes.
8. Do not infer undocumented writes or enable runtime write operations from vendor configuration tables.

See [`REFERENCE.md`](REFERENCE.md) for concise protocol notes and [`../../catalog-maintenance.md`](../../catalog-maintenance.md) for the automated maintenance/review workflow.
