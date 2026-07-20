# Strategy-Style Walk-Forward Artifact V1

## 1. Purpose

This artifact applies the frozen forward-outcome and walk-forward contract to
the deterministic strategy-style event facts. It calculates event outcomes,
four annual out-of-time summary layers, episode diagnostics, profile support,
and the final mechanism decision in one offline build.

It does not rebuild events, fit parameters, design allocations, simulate a
portfolio, calculate costs, or integrate with `CURRENT_TAA`.

## 2. Formal Command

```powershell
python scripts/build_strategy_style_walk_forward.py --as-of 2026-07-15
```

The date is mandatory and frozen. Any other date fails before publication.

## 3. Formal Inputs

The builder reads only:

- `data/strategy_style_logic_events_v1/manifest.json`
- `data/strategy_style_logic_events_v1/events.json`
- `data/strategy_style_category_calculations_v1/common_panel.json`
- `docs/STRATEGY_STYLE_FORWARD_OUTCOME_WALK_FORWARD_PREREGISTRATION_V1.md`
- `docs/STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1.md`
- `docs/STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md`

The event file is the only event source. The five raw total-return `close`
arrays in the common panel are the only return source. All six formal files are
validated against frozen SHA-256 and byte-count identities. The builder does
not use network services, credentials, category states, daily logic, raw price
directories, earlier results, ETF data, execution data, or Web data.

## 4. Event Outcomes

Each of the 1122 events produces one record in the same order as the formal
event array. The result reference point is the common-session index immediately
after the event start. H20, H60, and H120 end exactly 20, 60, and 120 common
sessions later. A horizon that extends beyond the sample is
`UNAVAILABLE_AS_OF` with null end and result fields.

Closed-event episodes run from the delayed start through the common-session
index immediately after the exit observation. Open-event episodes are
`NOT_CLOSED`. No event result represents a trade or a portfolio return.

Growth, value, and cash flow use their single total-return member. Dividend
uses the arithmetic mean of the two separately calculated member returns.
Peer return is the arithmetic mean of the other three style units, with the
dividend family counted once.

## 5. Time Partitions

The only partitions are:

- `DEVELOPMENT_EXCLUDED` for 2013 through 2017.
- `FORMAL_OOS` with `WF_2018` through `WF_2025`.
- `PROSPECTIVE_NOT_SCORED` for 2026 through the frozen as-of date.

Only formal OOS events enter the four walk-forward summary layers and episode
diagnostics. No fold changes formulas or profile parameters.

## 6. Walk-Forward Summaries

The artifact produces these fixed layers:

- 288 profile-style-fold-horizon rows.
- 36 profile-style-horizon rows.
- 72 profile-fold-horizon rows.
- 9 profile-horizon rows.
- 12 profile-style episode rows.

Medians use raw floating-point values. Folds and styles receive equal weight at
their respective aggregation levels; event counts are never used as fold or
style weights. Empty units remain explicit and are not converted to zero.

## 7. Profile Decision

H60 is the primary horizon. Each profile is evaluated against the frozen style
breadth, annual consistency, primary-direction, and secondary-confirmation
conditions, including the minimum of five available folds. Supported profiles,
if any, are compared by the frozen all-candidate reduction algorithm. The only
mechanism decisions are `REJECTED`, `AMBIGUOUS`, and `SUPPORTED`.

The implementation reports the frozen decision; it does not adapt parameters
or promote an unsupported mechanism. A rejected or ambiguous mechanism cannot
proceed to allocation design.

## 8. Outputs

The command atomically replaces `data/strategy_style_walk_forward_v1/` with
exactly:

- `manifest.json`
- `event_outcomes.json`
- `walk_forward_summary.json`

The manifest records formal source identities, output hashes and byte counts,
fixed invariants, implementation statuses, and the same decision as the
summary. It does not record its own hash.

## 9. Reproducibility and Publication

All JSON uses UTF-8, sorted keys, finite values only, fixed array ordering, and
one trailing newline. No generation timestamp is included. The three files are
written and validated in a same-filesystem staging directory before the output
directory is replaced. A failed replacement restores the prior complete
directory.

## 10. Boundary

The artifact contains no prices labeled as execution prices, positions,
weights, allocations, capital, transaction costs, portfolio returns, equity
curves, drawdown statistics, performance ratios, win rates, or rankings.

Its terminal statuses remain:

```text
Forward outcome implementation status: IMPLEMENTED
Forward outcome dataset status: BUILT
Walk-forward status: RUN
Profile selection execution status: RUN
Allocation status: NOT_DEFINED
Backtest status: NOT_RUN
Integration status: DO_NOT_INTEGRATE
```
