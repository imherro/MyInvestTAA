# Data Contracts

## Date contract

`market_data_as_of` is the last market-data date. `decision_date` is the human decision date and cannot be earlier. `generated_at` is an explicit timezone-aware build parameter. No current clock value may affect release JSON.

## Identifier contract

Execution instruments use the `tushare_ts_code` namespace: six digits plus `.SH` or `.SZ`, with `CASH` as the only special value. The alias registry rejects chains, cycles, namespace shadowing, canonical collisions, unresolved positive weights, missing source metadata, and invalid instrument types.

## Weight contract

Research, V11, Execution, and Shadow weights reconcile independently. CASH is explicit. V11 and Shadow are displayed side by side and are never merged. The Current Decision verifies source hashes, V11 semantic integrity, identifier normalization, temporal consistency, execution evidence, and Shadow constraints.

## Release contract

Every manifest input and artifact records path, role, raw SHA-256, semantic hash where applicable, source date, classification, and dependencies. Classifications are `rebuilt_artifact`, `immutable_governance_artifact`, and `verified_external_local_input`.

The two release APIs are read-only:

- `GET /api/system/release-manifest`
- `GET /api/system/acceptance`

Missing or invalid files return `available=false` instead of triggering a build or network request.
