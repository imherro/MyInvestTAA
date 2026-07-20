# Drawdown Add-On Trigger Candidate V1

## Purpose

`reports/strategy_research/drawdown_addon_trigger_candidate_v1.json` defines a
fixed three-level drawdown trigger candidate for the five analyzed Tier-A
assets. It is a research rule description, not an allocation, position-sizing
rule, order, backtest result, or formal system input.

## Source Boundary

The builder reads only
`reports/strategy_research/drawdown_threshold_evidence_table.json`. It does not
read prices, earlier drawdown research layers, configuration, CURRENT_TAA,
execution, Shadow, release, or Web inputs. Evidence values are copied from the
compact table and are not recomputed.

## Fixed Tiers

All analyzed assets use `completed_event_depth_quantile`. The three levels are
fixed before evaluating results:

1. Tier 1: `p75`
2. Tier 2: `p90`
3. Tier 3: `p95`

The same family and levels apply to every analyzed asset. One- and two-year
returns do not select or optimize the thresholds.

## Event Semantics

At a new drawdown event's peak date, each threshold is computed from historical
events that were already complete. The three thresholds are frozen for that
event. A tier triggers the first time drawdown reaches or exceeds its threshold,
at most once per event. Reaching a deeper tier preserves shallower-tier trigger
state. Recovery to the original peak resets all three states for the next event.
A tier with insufficient historical evidence does not trigger.

These semantics describe trigger facts only. They do not define capital amounts,
total equity exposure, selling, recovery allocation, or trading instructions.

## Output Contract

The report records the source evidence-table SHA-256 and source ledger hash. It
contains exactly five analyzed assets with three tiers each and exactly two
blocked assets without tiers. For each tier, current and median historical depth,
attainment counts and rate, one-year evidence, two-year evidence, and
post-trigger additional-loss evidence are copied directly from the matching
compact-table row.

## Non-Goals

This candidate does not rank assets or thresholds, choose optimal parameters,
size positions, backtest a portfolio, generate orders, or change CURRENT_TAA,
ETF mapping, Shadow, execution, release, or Web behavior.
