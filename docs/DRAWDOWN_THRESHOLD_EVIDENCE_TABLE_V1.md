# Compact Drawdown Threshold Evidence Table V1

## Purpose

`reports/strategy_research/drawdown_threshold_evidence_table.json` is a compact
summary of the formal P1-Task-06 walk-forward ledger. It is research evidence,
not a strategy, ranking, parameter-selection rule, allocation, or Web input.

## Source Boundary

The builder reads only `reports/strategy_research/drawdown_walk_forward_evidence`.
The ledger index and seven Tier-A asset reports are the sole formal facts. The
builder does not read prices, drawdown events, outcomes, cohorts, statistics, or
configuration inputs, and it does not recompute the P1-Task-06 research chain.

## Output Shape

The output contains the source ledger index SHA-256, a fixed 7 / 5 / 2 summary,
two blocked-asset entries, and exactly 75 rows. Rows are ordered first by the
ledger research-asset order and then by the ledger's fifteen threshold groups.
Blocked assets have no rows.

Each row preserves the asset and threshold identity, threshold attainment facts,
the latest and R-7 median observed threshold depth, observed/censored 252- and
504-session forward returns, and realized/censored post-trigger additional loss.

## Attainment

`resolved_attainment_count` is `reached_count + completed_not_reached_count`.
Open events that have not reached a threshold and insufficient-history events do
not enter that denominator. Open events that have reached a threshold are known
reach facts and do enter `reached_count`.

## Returns And Additional Loss

One- and two-year fields use only 252 and 504 sessions. Only observed horizons
enter return distributions; censored horizons are counted separately. Positive
returns are strictly greater than zero.

For realized minimum outcomes, additional loss is `max(0, -additional_return)`.
Censored minima do not enter the loss distributions. All medians and p75 values
use the existing R-7 linear quantile implementation.

## Non-Goals

This artifact must not score, rank, eliminate, or select thresholds. It must not
create positions, define an allocation, backtest a strategy, or change the
CURRENT_TAA, execution, Shadow, release, or Web layers.
