# Research Universe Contract V1

## Authority

`config/research_universe_v1.json` is the executable research allowlist. Its human reference is `docs/MyInvestTAA_全收益指数研究资产范围_V1.0.docx`.

The contract contains exactly 32 assets: 7 tier A, 12 tier B, and 13 tier C. It does not activate those assets in the current runtime configuration.

## Identity Fields

- `asset_key`: stable lowercase ASCII system identity.
- `official_code`: code in the approved human reference.
- `provider_code`: verified Tushare query code, or `null` when unknown.
- `display_name`: approved Chinese index name.
- `research_order`: fixed research sequence and part of contract semantics.

Provider-code changes do not change `asset_key`. Unknown mappings remain blocked and cannot be filled with similar indexes.

## Classification Fields

- `tier`: `A`, `B`, or `C`.
- `asset_group`: `broad_base`, `style`, or `industry`.
- `risk_family`: portfolio-level correlated exposure family.
- `return_basis`: always `total_return`.
- `data_source`: always `tushare` for the formal data path.

## Status Fields

- `verification_status`: `verified`, `unverified`, or `unavailable`.
- `research_status`: `pending`, `available`, or `blocked`.
- `substitution_allowed`: always `false`.

An unverified provider cannot be marked available. A provider query that returns data proves availability only; total-return basis remains a separate evidence decision.

## Hash

The universe hash is SHA-256 over canonical JSON:

```python
json.dumps(
    contract,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
```

Asset array order is semantic and follows `research_order`. Formatting whitespace does not affect the hash.

## Audit Modes

`python scripts/audit_research_universe.py --offline` validates the contract and A-tier local caches without network access.

`python scripts/audit_research_universe.py --provider-check` queries A-tier provider codes through the existing Tushare data source. It never writes market caches, runs CURRENT_TAA, downloads ETF data, or searches for replacements.

The generated report is `reports/strategy_research/universe_audit.json`. B-tier and C-tier assets are contract-validated but are not queried in P0.
