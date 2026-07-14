# Offline Build

## Required command

```powershell
python scripts/build_system_release.py --market-data-as-of 2026-07-08 --decision-date 2026-07-13 --generated-at 2026-07-13T08:15:34+00:00 --provider local --output-dir reports/release
```

The dates and timestamp are mandatory. The build rejects `mock`, live providers, missing local inputs, protected-file drift, incomplete execution evidence, invalid V11 semantics, unresolved instrument identifiers, and production-boundary violations.

## What is rebuilt

- V11 current allocation
- Current Market Decision
- UI route inventory and cleanup evidence
- System acceptance report
- Release manifest and committed marker

Strategy Diagnosis, Research Backtest, Execution Backtest, Execution-Aware Shadow, approval records, and local price provenance are verified local inputs or immutable governance artifacts. The release snapshots them without network access.

## Determinism

The orchestrator builds the candidate twice in separate staging directories. Raw JSON hashes, semantic hashes, the manifest, and the dependency graph must match. Only a verified candidate is promoted to `reports/release/current/`.

Verify it with:

```powershell
python scripts/verify_system_release.py
```
