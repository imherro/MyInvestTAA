# Execution Engine V2

## Status and boundary

Execution Engine V2 is experimental validation only. It does not replace Execution V1, enter Current Decision, change mapping approvals, or participate in the formal release gate. It never produces orders, quantities, shares, amounts, or target prices.

## B1 daily order

Each master-calendar trading day is processed in this fixed order:

1. Mark held ETFs to the current verified price. A missing held price retains the last verified valuation and records a stale valuation.
2. Retry pending held-asset adjustments whose current price is available.
3. Process a newly scheduled research signal. Signals are scheduled no earlier than the next local trading day.
4. Record end-of-day NAV, actual weights, cash, stale assets, and pending adjustments.

A new signal supersedes unresolved adjustments from an older signal. Superseded records remain in the audit history.

## Requested, actual, and deferred state

Every signal event separates:

- `requested_target_weights`: translated research targets, including requested cash.
- `executable_target_weights`: targets that can be traded on the scheduled date.
- `actual_post_trade_weights`: actual ETF and cash weights after the partial or complete rebalance.
- `deferred_adjustments`: held-asset target differences that cannot trade because the ETF price is missing.
- `cash_breakdown`: research cash and target weights that genuinely remain cash because no executable entry exists.
- `reconciliation`: requested, actual, cash, and deferred weight checks.
- `first_attempt_snapshot`: immutable evidence from the scheduled execution date.
- `completion_snapshot`: final evidence from the recovery date, when all pending adjustments complete.
- `terminal_status`: `completed`, `superseded`, or `open` while an adjustment remains pending.

A frozen holding is never also counted as `missing_entry_price_cash`. Pending reductions, exits, or increases retry on the first verified-price day. An unheld ETF with no entry price remains cash and is not automatically chased later.

## Comparison views

The V1/V2 report is neutral attribution and exposes three views:

- `legacy_as_reported`: each historical report on its original date grid.
- `exact_shared_observation_dates`: both curves restricted to the identical date set, with equal observation counts and a date-set hash.
- `master_calendar_aligned`: V2 master-calendar dates with V1 NAV carried forward for missing V1 observations. This is analysis-only and does not reconstruct V1 trading.

Date metrics include both observation-count annualization and elapsed-calendar-time annualization. Direct Sharpe comparisons use the exact shared date grid.

## Output integrity

The three V2 artifacts are written to a staging directory, re-read, and cross-validated. They share one deterministic `run_id` and `input_source_manifest_hash`. Validation proves that report daily states and curves equal the master-calendar grid, every timeline instrument covers every master date, and the comparison exact-date hash can be reproduced. The writer then records raw and semantic hashes in `reports/execution_v2_output_manifest.json` and commits the set with `reports/execution_v2_COMMITTED.json`. Promotion restores the previous valid set if any replacement fails.

The Web/API loader fails closed unless the marker, manifest, all artifact hashes, current input hashes, timeline summary, comparison equality, strategy ID, and experimental boundary all verify. Integrity failure returns a read-only unavailable response instead of partial data or an HTTP 500.

## B1 golden freeze

`reports/execution_v2_b1_golden.json` freezes the B1 periods, gross/net metrics, gross/net curves, coverage contract, and gap metrics as one semantic business payload. Domain-contract or audit-schema changes must reproduce the same payload hash before cost or cash-yield work can begin. Internal rebalance and pending paths use the dataclasses in `backtest/execution/v2/domain.py`; outward JSON remains explicit and stable.

## B2-1 transaction costs

B2-1 is a separate experimental scenario layered on the verified B1 output set. It does not rewrite B1 artifacts or change the Web/API, Current Decision, mapping approvals, or formal release gate. Its commission and slippage rates are explicit research assumptions, not a broker fee schedule or observed market-impact evidence. ETF fund expenses remain embedded in adjusted market prices, taxes are explicitly configured, and cash yield is fixed at zero.

Costs are calculated only from executed pre-trade and post-trade notional differences. A deferred adjustment incurs no cost while pending and is charged only on its completed recovery date. Sales execute before buys; buy notional is proportionally reduced when transaction costs would otherwise require borrowing. The ledger records the parent event, optional pending-adjustment ID, instrument, direction, pre/requested/executed values, gross notional, cost components, policy hash, and mapping quality.

The B2-1 report preserves B1's exact date grid and includes a daily accounting bridge, cumulative cost curve, instrument/year/mapping-quality attribution, observation-count and elapsed-calendar annualization, and turnover stated in initial-NAV units. Its deterministic run ID binds the B1 input and output identities, cost-policy hash, scenario, date grid, strategy, and all cost-engine source hashes. A separate staged output set and commit marker fail closed on source or artifact tampering.
