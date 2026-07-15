# Execution Mapping Strategy

Status basis: local reports through 2026-07-08. This document describes research-to-ETF mapping governance; it does not approve trades or change strategy weights.

## Current Coverage

The research universe contains 33 assets. Fourteen total-return research indices are currently eligible for allocation, while the 18 Shenwan price indices and `399606.SZ` remain monitoring-only.

Among the 14 allocation-eligible total-return indices:

| Mapping state | Count | Research assets |
| --- | ---: | --- |
| High-quality ETF proxy | 5 | `H00300.CSI`, `H00905.CSI`, `H00852.CSI`, `000688CNY01.CSI`, `480092.CNI` |
| Medium-quality ETF proxy | 5 | `H00015.CSI`, `H00922.CSI`, `H20007.CSI`, `931743CNY010.CSI`, `H20771.CSI` |
| Low-quality proxy, excluded from execution | 1 | `H00805.CSI` |
| No approved proxy | 3 | `H21152.CSI`, `H20590.CSI`, `931688CNY010.CSI` |

`399606.SZ` also has a high-quality ETF proxy, but the research asset remains ineligible pending its research-data audit.

The latest execution backtest reports:

- Mapping-weight coverage: 69.3365%.
- Tradable-weight coverage: 69.1469%.
- Unmapped cash: 8.7879% on average.
- Low-quality-proxy cash: 15.7197% on average.
- Untradable-month ratio: 100%, because the current metric marks a month whenever any positive weight is unmapped, low-quality, missing-price, or otherwise untradable.

The latest Shadow allocation has 30% strategy cash and a further 10% research-only cash from `931688CNY010.CSI`. Its 60% ETF exposure is not a production portfolio.

## Decision On Research Indices

Do not replace a research index merely because it lacks a convenient ETF. The research layer measures the intended economic exposure over a long history; the execution layer measures whether that exposure can be implemented after ETF inception.

Replace an underlying research index only when all of the following are true:

1. The replacement has the same intended economic exposure and return basis.
2. Its methodology and constituent scope are at least as suitable for the research question.
3. The change improves data quality or investability rather than only improving a coverage statistic.
4. The strategy is rerun as a new governed version, with old and new results compared side by side.

## Mapping Rules

Use semantic validation before statistical validation:

1. Direct tracker: the ETF tracks the same index or an explicitly equivalent index. This can qualify as high quality.
2. Close thematic proxy: methodology, constituent overlap, sector exposure, and return behavior all pass documented thresholds. This can qualify as medium quality after manual approval.
3. Broad or cross-theme proxy: correlation alone is insufficient. Keep it research-only or low quality.
4. Missing proxy: convert the affected execution weight to cash and disclose the reason. Never silently substitute a broad-market ETF.

Candidate selection should also check inception date, adjusted-price history, liquidity, scale, tracking error, fee drag, and collisions where one ETF represents several research exposures.

## Priority Work

1. Expand the execution candidate universe with direct innovation-drug, robotics, computing-power/data-center, and broader resource-cycle ETFs before rerunning proxy research.
2. Reassess `H00805.CSI` with either a true resource ETF or a governed multi-ETF resource basket. `512400.SH` alone represents nonferrous metals, not the full resource exposure.
3. Keep the rejected broad proxies frozen until new semantic evidence exists. Current statistical proposals such as computing power to semiconductor, robotics to CSI 1000, or innovation drug to ChiNext do not establish exposure equivalence.
4. Add an execution-aware concentration limit for research-only and low-quality weights as a separately governed constraint; do not alter the pure research backtest retrospectively.
5. Report both the strict any-gap month ratio and a material untradable-weight month ratio. Do not relax the existing production gate merely to make the current report pass.

## Display Contract

HTML pages display registered ETF identifiers as `code name`, for example `512760.SH 半导体ETF`. JSON APIs retain canonical codes only so their machine-readable contracts remain stable.
