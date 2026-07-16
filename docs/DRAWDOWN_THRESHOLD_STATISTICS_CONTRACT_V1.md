# Drawdown Threshold Statistics Contract V1

## Purpose

This layer aggregates the audited threshold cohorts within one asset, one
threshold family, and one threshold level. It describes threshold availability,
attainment, censoring-aware recovery, fixed-window outcomes, and realized
post-trigger minima. It does not rank thresholds or define a strategy.

## Statistical unit

Each analyzed asset has 15 independent report groups in the fixed cohort order.
Every event contributes at most one cohort to a group. Only `reached` cohorts
enter post-trigger statistics. `not_reached` and `insufficient_history` are not
recovery failures and never enter recovery, return, or minimum distributions.

Coverage is defined as:

```text
threshold_available = reached + not_reached
attainment_rate = reached / threshold_available
```

The rate is null when no event has a calculable threshold. It is an empirical
attainment fraction, not an investment success probability.

## Recovery and censoring

Every reached cohort joins exactly one formal outcome through
`selected_record_id`. Trigger-price and peak-recovery samples are calculated
separately. Observed samples use the formal `sessions_from_trigger`; censored
open-event samples use:

```text
last_visible_series_index - trigger_series_index
```

A completed event with censored recovery is invalid and fails closed.

Kaplan-Meier processing uses unique session times in ascending order. At a
shared time, observed recoveries are applied to survival before censorings are
removed from the risk set:

```text
S(t) = S(previous) * (1 - d_t / n_t)
```

The Greenwood sum adds `d_t / (n_t * (n_t - d_t))` only when `n_t > d_t`.
The standard error is zero when survival reaches zero. No confidence interval
is produced. Median recovery is the first session where survival is at most
0.5, otherwise null.

KM estimates are also read at 63, 126, 252, 504, and 756 trading sessions.
An empty reached sample has null probabilities.

## Fixed-window outcomes

For each fixed horizon, observed and censored windows are counted separately.
Only formal `observed` windows enter distributions of forward return, maximum
adverse excursion, and maximum favorable excursion. Partial windows and the
last available date are never substituted for the formal horizon endpoint.

Distributions contain minimum, R-7 p25/p50/p75, maximum, and mean. Forward
returns also contain strictly positive and non-negative counts and rates.

## Continued decline

Only `minimum_outcome.status == realized` records enter additional-return and
sessions-to-minimum distributions. Open-event censored minima are counted but
excluded. This exclusion does not remove censoring bias and does not imply that
an open event cannot decline further.

## Point-in-time contract

`build_threshold_statistics(..., as_of_date=t)` requires an actual input trading
date, truncates the daily series immediately at that row, keeps only visible
`date` and `close`, and rebuilds event, outcome, and cohort facts. Future rows,
events, recoveries, threshold crossings, and completed windows cannot affect an
earlier as-of result.

## Formal sources

The report builder reads the universe and audit plus exactly eight JSON files in
each of the event, outcome, and threshold-cohort directories. It does not read
price caches, drawdown profile reports, ETF data, or substitute indexes.

Before publication it rebuilds the formal outcome and cohort business content,
checks every source hash and summary, and validates every selected-record join.
Any stale hash, open source set, altered business fact, identity mismatch, or
invalid blocked fact fails closed.

## Publication and limitations

The output directory contains exactly one index and seven Tier-A reports. Five
assets are analyzed; the two blocked assets retain empty statistics and their
source blockers. Reports are staged, validated, and atomically replace the prior
complete directory.

- Candidate thresholds are not formal strategy parameters.
- Groups are not pooled across assets, families, or levels.
- Different threshold groups from the same event are highly dependent.
- Kaplan-Meier relies on an unproven non-informative censoring assumption.
- Small samples are unstable; naive observed fractions are not KM estimates.
- No threshold ranking, position, exit rule, trade instruction, or strategy
  performance is produced.
