# Data Contracts

## Date contract

`market_data_as_of` is the last market-data date. `decision_date` is the human decision date and cannot be earlier. `generated_at` is an explicit timezone-aware build parameter. No current clock value may affect release JSON.

## Identifier contract

Execution instruments use the `tushare_ts_code` namespace: six digits plus `.SH` or `.SZ`, with `CASH` as the only special value. The alias registry rejects chains, cycles, namespace shadowing, canonical collisions, unresolved positive weights, missing source metadata, and invalid instrument types.

## Weight contract

Research, V11, Execution, and Shadow weights reconcile independently. CASH is explicit. V11 and Shadow are displayed side by side and are never merged. The Current Decision verifies source hashes, V11 semantic integrity, identifier normalization, temporal consistency, execution evidence, and Shadow constraints.

## Execution coverage and gap contract

`tradable_weight_coverage` divides translated tradable ETF weight by the Research allocation's non-cash weight. It is not a percentage of the whole portfolio. `tradable_weight_coverage_total_portfolio` provides the whole-portfolio denominator separately.

The legacy `untradable_month_ratio` remains the execution gate metric and is also exposed as `binary_any_gap_month_ratio`. A month is counted when any positive weight is unmapped, mapped only to a low-quality proxy, missing a usable price, or otherwise untradable. It does not mean the whole portfolio was untradable. Continuous severity is reported through average, median, and maximum gap weight, threshold month ratios, and a reason breakdown. Adding these fields does not change the existing gate.

## Research universe scope contract

`universe_count` counts available allocation-eligible total-return or net-return assets after readiness validation. `universe_scope` records all registered assets, the exact included IDs, and every excluded or unavailable asset with its reason. Monitor-only `399606.SZ` remains registered but is excluded from the current allocation backtest.

## Counterfactual validity contract

A mapping counterfactual is current evidence only when its recorded SHA-256 values match the current asset mapping, decision ledger, approval integrity seal, and execution backtest report. A missing or mismatched baseline contract forces `status=stale`, `evidence_use=historical_only`, and disables manual mapping approval readiness in the loader and API.

## Release contract

Every manifest input and artifact records path, role, raw SHA-256, semantic hash where applicable, source date, classification, and dependencies. Classifications are `rebuilt_artifact`, `immutable_governance_artifact`, and `verified_external_local_input`.

The two release APIs are read-only:

- `GET /api/system/release-manifest`
- `GET /api/system/acceptance`

Missing or invalid files return `available=false` instead of triggering a build or network request.
