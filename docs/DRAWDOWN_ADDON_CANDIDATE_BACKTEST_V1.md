# Drawdown Add-On Candidate Backtest V1

## Purpose

`reports/strategy_research/drawdown_addon_candidate_backtest_v1.json` tests the
fixed P1-Task-09 drawdown rule without selecting assets, thresholds, or weights.
It is independent research evidence, not CURRENT_TAA, an ETF instruction, or an
execution input.

## Fixed Portfolio Rule

Each analyzed total-return index is tested independently. The normal portfolio
is 70% index and 30% zero-return cash. The fixed p75, p90, and p95 event tiers
raise the target to 80%, 90%, and 100%. A formal recovery to the event peak
resets the target to 70%. A bounce that does not recover the peak does not
reduce exposure, and an open event never resets.

The first close initializes the portfolio. A tier or recovery observed at close
is executed at the next actual trading-day close; a signal without a following
session is skipped. If several tiers are first reached on one day, only the
deepest target is executed. Each tier can be reached only once within an event.
There is no daily rebalancing.

## Accounting

The strategy starts with NAV 1.0 and maintains explicit index units and cash.
Each allowed trade, including initialization, pays 10 basis points one way on
the absolute change from the pre-trade actual index weight. Cost is deducted
before units and cash are reset to the new target. Cash earns zero and may not
be negative except for numerical tolerance.

The static 70/30 and 100% buy-and-hold benchmarks initialize at NAV 1.0 without
transaction cost and never trade again. Total return and CAGR use initial
capital 1.0. Annualized volatility uses population standard deviation of daily
close-to-close returns and 252 sessions per year. Maximum drawdown includes
initial capital as the first high-water mark; Calmar is CAGR divided by the
absolute maximum drawdown, or zero when maximum drawdown is zero.

## Source Boundary

The runner reads only the pre-registered candidate, the walk-forward evidence
index and its seven asset reports, and the drawdown-event index and its seven
asset reports. Historical decisions use event-level `threshold_status` and
`trigger_date`; current reference depths in the candidate are never used as
historical signals. Both source directories must contain exactly eight JSON
files including their indexes, and all recorded source hashes and event
identities must agree.

Five assets are analyzed independently. The two blocked assets retain their
blockers and have no backtest result. The report contains no aggregate score,
optimization, selection, or pass/fail conclusion.
