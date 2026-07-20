# Drawdown Profile Contract V1

## Purpose

This layer turns the approved A-tier drawdown event facts into descriptive depth
and duration profiles. It does not create signals, allocations, recovery
probabilities, forward returns, ETF mappings, Shadow positions, or Web output.

## Source chain

Formal inputs are the current research-universe contract, its audit, and exactly
eight files in `reports/strategy_research/drawdown_events/`: the index and seven
A-tier asset reports. Price caches are not profile inputs.

The builder fails closed unless:

- universe identity and hash match the event index;
- the raw audit SHA-256 matches the event index;
- the event index contains exactly the seven A-tier assets in `research_order`;
- provider code, risk family, status, and report identity match the current
  universe and event index;
- all event reports retain the recorded universe and audit source chain;
- the event index summary can be reproduced from the seven reports.
- the event source directory contains exactly the index and seven approved asset
  JSON files; extra JSON makes the source set ambiguous and is rejected.

The output index records the raw event-index SHA-256. Each asset profile records
the raw SHA-256 of its event report.

## Depth semantics

Event facts store non-positive drawdown. Profiles expose positive depth:

```text
depth = max(0, -drawdown)
completed_event_depth = -max_drawdown
```

Daily depth must be in `[0, 1)`. Completed and open event maximum depth must be
in `(0, 1)`. NaN, infinity, positive drawdown, and a loss of 100% or more are
invalid.

## Samples

Daily profiles contain all observations and underwater-only observations.
Underwater sample size must equal the sum of event
`underwater_observations`. Event-depth and duration distributions contain only
completed events. An open event is right-censored and is reported separately.
Excluding it does not remove censoring bias; this version does not implement
survival analysis.

Depth percentiles are `p50`, `p60`, `p70`, `p75`, `p80`, `p85`, `p90`, `p95`,
and `p97_5`. Duration percentiles are `p50`, `p75`, `p90`, and `p95`.
Quantiles use deterministic R-7 linear interpolation:

```text
h = (n - 1) * p
q = x[floor(h)] + (h - floor(h)) * (x[ceil(h)] - x[floor(h)])
```

Empty distributions use `null` for summary values; one-value distributions
return that value at every percentile. Output is rounded to at most ten decimal
places and negative zero is normalized to zero.

Current historical position uses inclusive empirical comparisons:

```text
percentile = count(sample <= current) / sample_count
exceedance = count(sample >= current) / sample_count
```

## Point-in-time rule

`build_drawdown_profile(report, as_of_date=...)` requires an actual date in the
raw drawdown series. It locates that row without parsing later rows, extracts
only `date` and `close` from the visible prefix, and calls the approved
`analyze_drawdown_history(..., as_of_date=None)` engine. It never filters the
full event list because future trough and recovery facts would leak.

Legal or malformed rows and event facts after the requested date must not alter
the same historical profile. Errors in the visible prefix still fail. A full
profile validates the complete series, events, counts, states, dates, event IDs,
durations, and recovery fields.

The profile layer does not identify a second set of events. It validates every
supplied event against the approved daily facts: event and peak identity, indexed
date order, first underwater row, first deepest trough, maximum drawdown,
per-event underwater count, decline/recovery/span algebra, recovery-row semantics,
and the final state of an open event. Durations are verified from daily-series
indexes, not trusted as independent inputs.

## Output and publishing

`scripts/build_a_tier_drawdown_profiles.py` produces exactly eight JSON files in
`reports/strategy_research/drawdown_profiles/`: `index.json` plus seven A-tier
asset profiles. Five currently analyzed assets receive full profiles; the two
blocked assets receive null profile sections and retain their blockers.

Publishing writes and validates a sibling staging directory before replacing
the target directory. A failure preserves the previous complete target and
removes temporary output.
