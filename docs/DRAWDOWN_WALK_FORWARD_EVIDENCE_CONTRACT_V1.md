# Drawdown Walk-Forward Evidence Contract V1

## Purpose

This ledger separates every drawdown event into a strictly prior training
snapshot and a current-event evaluation. It preserves expanding-window,
out-of-sample evidence for later research. It does not score, rank, or select
thresholds and does not define positions, exits, or strategy returns.

## Time isolation

For event `e`:

```text
training_cutoff_date = event.peak_date
```

Training evidence is rebuilt by calling
`build_threshold_statistics(asset_event_report, as_of_date=event.peak_date)`.
The current event has not started at that date and cannot enter training
coverage, recovery samples, windows, or minima. Therefore:

```text
prior_event_count = event_sequence - 1
```

The first event always has zero prior events. Later event facts cannot revise an
earlier training snapshot.

## Training snapshot

Every event has a stable snapshot ID:

```text
{asset_key}:{event_sequence}:{peak_date}
```

The snapshot contains 15 groups in the fixed threshold-family and level order.
Each compact group retains coverage, compact recovery summaries and fixed KM
horizons, realized-minimum statistics, and fixed-window outcome distributions.
It omits KM samples and full timelines to control report size.

`training_group_sha256` binds the compact entry to the complete as-of statistics
group, including omitted KM samples, timelines, horizons, and distributions. It
uses SHA-256 over canonical JSON encoded as UTF-8 with `ensure_ascii=False`,
`sort_keys=True`, separators `(",", ":")`, and `allow_nan=False`.

## Current-event evaluation

Every event has exactly 15 test evaluations. The stable ID is:

```text
{asset_key}:{event_sequence}:{threshold_family}:{threshold_level}
```

The test cohort copies the required fields from the formal cohort report.
`insufficient_history` and `not_reached` have no selected record and a null test
outcome. `not_reached` is not a recovery failure or negative-return sample.

A `reached` cohort must select exactly one formal outcome. Its compact test
outcome copies the formal trigger identity, minimum result, both recovery
results, and all five fixed windows. No second outcome calculation is created.

## Point-in-time interface

`build_walk_forward_evidence(..., as_of_date=t)` requires an actual input trading
date, truncates immediately at that row, keeps only visible `date` and `close`,
and rebuilds event, outcome, cohort, and statistics facts. Only events started
by the target date appear. Future recoveries, windows, events, and malformed
future content cannot affect an earlier ledger.

## Formal sources and validation

The builder reads exactly eight JSON files from each formal event, outcome,
cohort, and statistics directory plus the universe and audit chain. It reads no
price cache, profile report, ETF data, or substitute index.

Before publication it rebuilds formal outcome, cohort, and full-history
statistics content; verifies all four source hashes, identities, statuses,
summaries, and blocked empty facts; recomputes each event's peak-date training
statistics; validates group hashes; and matches every test cohort and reached
test outcome to the formal source.

## Publication and limitations

The output directory contains exactly one index and seven Tier-A reports. Five
assets are analyzed and two retain their original blockers with empty ledgers.
Reports are staged, validated, and atomically replace the prior complete set.

- This is walk-forward evidence, not a strategy.
- The 15 evaluations within an event are highly dependent.
- Repeated events are not guaranteed to be independent or identically
  distributed.
- Small expanding-window training samples can be extremely unstable.
- No threshold reliability floor, score, rank, selection, position, trade
  instruction, exit, or strategy performance is produced.
- Later parameter research must use this ledger and must not substitute final
  full-history statistics for historical training evidence.
