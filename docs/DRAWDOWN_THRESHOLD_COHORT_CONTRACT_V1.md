# Drawdown Threshold Cohort Contract V1

## Purpose

This contract defines a point-in-time research library that links each drawdown
event to the first frontier record that reaches each candidate historical
drawdown threshold. It is a descriptive research layer, not a trading signal,
position rule, exit rule, or strategy backtest.

## Point-in-time rule

Every threshold for an event is frozen at:

```text
estimation_cutoff_date = event.peak_date
```

Only facts fully visible through that date may be used. The current event's
underwater observations and final depth are excluded from its own estimate.
Later lows, recoveries, and later completed events cannot revise a frozen
threshold.

Historical evaluation must use `build_threshold_cohorts(..., as_of_date=t)`.
The date must be an actual input trading date. The implementation truncates the
visible daily series immediately at that row, keeps only `date` and `close`, and
rebuilds events and frontier outcomes from the prefix.

## Candidate families

Each analyzed event produces exactly 15 rows in this order:

| Family | Levels | Historical sample | Formula |
| --- | --- | --- | --- |
| `underwater_daily_depth_quantile` | p75, p80, p85, p90, p95 | Underwater daily depths through the event peak | R-7 linear quantile |
| `completed_event_depth_quantile` | p75, p80, p85, p90, p95 | Event depths with recovery on or before the event peak | R-7 linear quantile |
| `historical_max_event_depth_fraction` | f50, f60, f70, f80, f90 | Same completed-event sample | Historical maximum times fraction |

Depth is the positive magnitude of negative drawdown. No arbitrary minimum
sample size is imposed. An empty sample produces `insufficient_history` and a
null threshold; any non-empty sample is calculated and retains its sample
count and visible date range.

## Crossing and deduplication

For each event and threshold, frontier records are read in ascending
`frontier_sequence`. The selected record is the first row satisfying:

```text
trigger_depth >= threshold_depth
```

Equality counts as reached. Later, deeper frontiers do not create duplicate
cohort rows. The allowed states are `insufficient_history`, `not_reached`, and
`reached`. A reached cohort references the formal outcome only through its
stable `selected_record_id` and copied trigger identity; it does not duplicate
outcome windows or recovery facts.

## Stable identity and order

The stable identifier is:

```text
{asset_key}:{event_sequence}:{threshold_family}:{threshold_level}
```

Rows are ordered by event sequence, fixed family order, and fixed level order.
Every analyzed event has exactly one row for each of the 15 candidates.

## Formal sources and fail-closed validation

The builder reads only:

- `config/research_universe_v1.json`
- `reports/strategy_research/universe_audit.json`
- the eight approved JSON files under `drawdown_events/`
- the eight approved JSON files under `drawdown_outcomes/`

It does not read price caches or generated drawdown profile reports. Before
publication it verifies both closed file sets, Tier-A order and identity, all
source hashes, event facts, blocked empty facts, source summaries, and a fresh
`build_drawdown_outcomes(event_report)` business recomputation. Any mismatch
fails closed.

## Publication

The output directory is
`reports/strategy_research/drawdown_threshold_cohorts/` and contains exactly an
index plus seven Tier-A asset reports. Five assets are analyzed and two retain
their source blockers with empty cohorts. Reports are staged, validated, and
then atomically replace the prior complete directory.

## Limitations

- Candidate thresholds are not approved strategy parameters.
- Rows from different thresholds within one event are highly dependent.
- A small historical sample does not establish reliability.
- No recovery probability, return aggregate, threshold ranking, position,
  exit rule, or portfolio performance is produced here.
- Full-history final quantiles and final maximum drawdowns must never be used
  as historical event thresholds.
