# Operations

## Start the read-only Web

```powershell
python backend/main.py
```

Open `http://localhost:8025/`. The Web reads local formal reports and `reports/release/current`; it never starts a build or fetches market data.

## Failed build

A failed build does not replace `reports/release/current`. Failure evidence remains in `reports/.release-staging/<build-id>/failure.json`.

## Recovery

```powershell
python scripts/recover_system_release.py
```

Recovery restores `reports/release/previous` only when current is missing or invalid and the previous release passes hash, marker, manifest, and acceptance verification.

## Staging cleanup

```powershell
python scripts/clean_release_staging.py
```

Failed staging directories are retained by default. Use `--include-failed` only after their error evidence has been reviewed.

## Stale or drifted data

Do not fall back to mock data or an older report. Rebuild the upstream local evidence with its formal script, verify its date and provenance, then run the release command again. Protected strategy, policy, mapping registry, and decision ledger files must not be automatically changed to make acceptance pass.
