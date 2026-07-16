# Drawdown Walk-Forward Diagnostic Contract V1

## Purpose

This contract defines a factual reliability diagnostic over the approved
A-tier expanding walk-forward evidence ledger. It does not score, rank, select,
approve, or reject thresholds and does not define positions, trades, or
strategy returns.

## Scope

Each analyzed asset is evaluated independently for the fixed fifteen groups:

- `underwater_daily_depth_quantile`: `p75`, `p80`, `p85`, `p90`, `p95`
- `completed_event_depth_quantile`: `p75`, `p80`, `p85`, `p90`, `p95`
- `historical_max_event_depth_fraction`: `f50`, `f60`, `f70`, `f80`, `f90`

No observations are pooled across assets, risk families, threshold families,
or levels. Each event contributes at most one evaluation to each group.

## Inputs and provenance

The report builder reads the approved universe and audit plus the closed
eight-file report sets for events, outcomes, cohorts, threshold statistics, and
walk-forward evidence. It does not read price caches, ETF data, substitute
indices, or drawdown profile reports.

Before publishing, the builder validates the universe identity, source index
hash chain, report identity and status, blocked-asset emptiness, and the formal
walk-forward ledger against a complete recomputation. That recomputation in
turn verifies the outcome, cohort, and statistics layers.

## Diagnostic semantics

### Status support

`threshold_available_count` equals reached evaluations plus completed
not-reached evaluations plus open not-reached censored evaluations.
Insufficient-history evaluations are excluded. An open reached evaluation is a
resolved positive; an open not-reached evaluation is unresolved and is never a
final negative.

### Training support and trajectories

Training support records integer trajectories for available events, reached
events, trigger and peak recovery samples, and observed fixed-window samples.
Metric trajectories cover attainment rate, ten fixed-horizon Kaplan-Meier
recovery probabilities, and five fixed-window forward-return medians. Summary
quantiles use the existing R-7 implementation. Null observations are skipped
and reported; adjacent changes are calculated only between adjacent defined
values.

Threshold-depth relative changes are
`abs(current - previous) / previous`. Every included previous depth must be
strictly positive. These values describe movement and are not a stability
score.

### Attainment prequential diagnostic

The training prediction is the event-time training attainment rate. Resolved
test labels are `1` for reached and `0` for completed not-reached. Open
not-reached and insufficient-history evaluations are excluded. The report
provides the mean prediction, observed frequency, calibration gap, absolute
calibration gap, and Brier score without comparing groups.

### Recovery prequential diagnostic

Trigger-price and peak recovery are evaluated at 63, 126, 252, 504, and 756
sessions. An observed recovery at or before the horizon is `1`; an observed
recovery after it is `0`. A censored recovery is `0` only when the visible
series extends through the horizon; otherwise it remains unresolved.

Only resolved observations with a defined training Kaplan-Meier probability
enter calibration and Brier calculations. Excluding observations censored
before the horizon creates complete-case bias; this is not an IPCW estimate.

### Forward-return prequential diagnostic

Only reached tests with an observed fixed window and defined training p25, p50,
and p75 enter comparison. Diagnostics report signed and absolute error against
training p50, sign agreement, and inclusion within the closed training IQR.
These are forecast diagnostics, not strategy returns.

## Point-in-time rule

When `as_of_date` is supplied, it must identify an actual input trading date.
The implementation immediately takes the inclusive visible prefix, rebuilds
events, outcomes, cohorts, statistics, and the walk-forward ledger, then
diagnoses only facts visible at that point. Later events, recoveries, windows,
and malformed future fields cannot influence the result. Therefore a report
built as of a date must equal a report built from the exact valid prefix.

## Output and publication

The output directory is
`reports/strategy_research/drawdown_walk_forward_diagnostics/` and contains
exactly `index.json` plus seven A-tier asset reports. An analyzed report contains
fifteen diagnostics in fixed order. A blocked report contains no period, groups,
or event facts and preserves its source blockers.

Reports are written to a same-parent staging directory with finite-number JSON
validation. The complete directory is replaced only after successful
validation; a failed build preserves the prior published directory and removes
temporary files.

## Limitations

- This is reliability evidence, not threshold ranking.
- There is no predefined pass, elimination, or minimum-sample rule.
- The fifteen evaluations within one event are highly dependent.
- Small-sample Brier scores and calibration gaps can be unstable.
- Open not-reached tests remain right-censored.
- Recovery complete-case diagnostics can be biased.
- Forward-return diagnostics include only complete test windows.
- Training drift can reflect sample growth rather than structural failure.
- Assets are not pooled.
- No parameter choice, allocation, execution, or strategy return is produced.
