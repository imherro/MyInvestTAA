# Drawdown Frontier Outcome Contract V1

## Scope

This layer records objective outcomes from approved A-tier drawdown events. A
frontier is the first underwater row or a later row whose drawdown is strictly
below every earlier underwater row in the same event. Equal lows and rebounds do
not create records. Multiple frontiers in one event are dependent path facts,
not independent samples or trading signals.

The formal inputs are the current universe, audit, and the closed eight-JSON
drawdown-event set. Price caches and drawdown-profile reports are not calculation
inputs. Analyzed event reports must pass the approved full profile validator;
blocked reports must retain empty events and series and a null current state.

## Outcomes

Records have deterministic IDs `asset_key:event_sequence:frontier_sequence` and
stable event/frontier ordering. Positive depth is `-drawdown`; later frontiers
must have positive depth increments.

Minimum outcome uses the first minimum close from trigger through event recovery
for completed events, or through the report end for open events. Open minimum
outcomes are censored. Trigger-price recovery is the first later session whose
close reaches the trigger close within the same event observation endpoint.
Peak recovery uses the official event recovery date; open events are censored.

The 63, 126, 252, 504, and 756 session windows use the asset's continuing daily
series and may extend beyond event recovery. A complete window includes trigger
and end sessions and reports forward return, minimum path return (MAE), and
maximum path return (MFE). An incomplete window has null result fields; it is not
filled with the last available session or natural-day interpolation.

## Point In Time

For `as_of_date`, the implementation locates the actual date and immediately
cuts an inclusive prefix. It reads only visible `date` and `close`, rebuilds
events with the approved event engine, and computes outcomes only from that
prefix. Future rows, events, current state, lows, recoveries, and complete windows
cannot leak into historical results. Visible-prefix errors still fail.

## Outputs

The builder atomically publishes exactly eight JSON files under
`reports/strategy_research/drawdown_outcomes/`. Source index and asset-report raw
SHA-256 values are recorded. Index references, record ordering and uniqueness,
and summaries are validated before replacement; failure preserves the previous
complete directory.

Observed does not imply future recovery, and censored does not imply eventual
failure. This version calculates no probability, aggregate statistic, threshold,
allocation, signal, backtest, ETF mapping, Shadow position, or Web output.
