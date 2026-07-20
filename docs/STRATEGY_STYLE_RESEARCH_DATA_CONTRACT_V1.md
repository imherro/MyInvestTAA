# Strategy-Style Research Data Contract V1

## Purpose

`data/strategy_style_research/` is a complete, independent Tushare snapshot for
future strategy-style research. It contains only growth, value, dividend, and
cash-flow total-return indexes. It is not an input to formal CURRENT_TAA, ETF,
Shadow, execution, release, or Web behavior.

The fixed universe is:

1. `CN2296.CNI` - 创成长R - growth
2. `CN2371.CNI` - 国证价值R - value
3. `H00015.CSI` - 红利收益 - dividend
4. `H00922.CSI` - 中红收益 - dividend
5. `480092.CNI` - 国证自由现金流指数R - cash flow

Broad-base, industry-theme, resource-cycle, and all other assets are excluded.
No asset can be substituted by name similarity.

## Source And Cutoff

The builder reads the token only from `TUSHARE_TOKEN` in the environment or the
project `.env`. It calls Tushare `index_basic` and year-chunked `index_daily`
for every asset, plus year-chunked SSE `trade_cal`. The formal V1 snapshot must
be built with an explicit `--as-of 2026-07-15`. Token and authorization values
must never appear in source, configuration, output, or logs.

All five assets are downloaded again for this snapshot. Existing files under
`data/research_prices/` are neither read nor copied. This controlled duplication
keeps provider, cutoff, generation time, calendar, format, and audit semantics
consistent within one independent data boundary.

## Metadata Contract

Each `index_basic` query must return exactly one row with matching `ts_code` and
official-code prefix, non-empty name, full name, market and category, and valid
eight-digit base and listing dates. `CN2296.CNI` and `CN2371.CNI` additionally
must match all metadata recorded in the universe configuration. The remaining
three assets use identity-only mode: returned metadata is recorded without
requiring its names to equal project display text.

## Price And Calendar Contract

Daily index history is queried by calendar year from the metadata base-date
year through the explicit cutoff. Rows from all chunks are combined and sorted;
any duplicate date fails the build. Every cache row contains only an ISO date,
a finite positive close, and `return_basis=total_return`.

The independent SSE open-session calendar begins at the earliest downloaded
price date and ends at the cutoff. For each asset, its price-date set must equal
the open-session set from that asset's first date through the cutoff. Missing,
extra, duplicate, stale, zero, negative, NaN, or infinite values block the whole
snapshot. No filling, deletion, normalization, or partial publication is
allowed.

## Publication Boundary

The dataset contains exactly one manifest, one calendar, and five price files.
The only qualification report is
`reports/strategy_research/strategy_style_data_qualification_v1.json`. The
manifest records metadata, query spans, source hashes, and row counts. The
report records every fixed qualification check and is `QUALIFIED` only when all
five assets pass. A blocked build exits nonzero and leaves any prior complete
snapshot unchanged.

This contract establishes data eligibility only. It does not define drawdown
events, triggers, allocation weights, walk-forward logic, or a backtest.
