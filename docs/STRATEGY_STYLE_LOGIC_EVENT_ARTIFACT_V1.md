# Strategy-Style Logic Event Artifact V1

## 1. Purpose

This artifact deterministically converts the frozen daily logic transitions into
event facts. It scans twelve independent `profile_id × style_unit` streams and
records closed or open logical intervals.

The artifact does not calculate prices, returns, outcomes, profile performance,
portfolio weights, execution, costs, or backtests. Event facts are not investment
actions and are not integrated with `CURRENT_TAA`.

## 2. Formal Command

```powershell
python scripts/build_strategy_style_logic_events.py --as-of 2026-07-15
```

The date is mandatory and frozen. The builder is offline and reads only the
daily-logic manifest, daily logic, common panel date axis, event contract, and
state-machine contract.

## 3. Validation Boundary

Before scanning, the builder validates the formal daily-logic manifest identity,
hash, byte count, statuses, and invariants. It also validates the daily logic,
common panel, both contracts, fixed profile/style/member order, all arrays,
enumerations, six legal transitions, recurrence, and concurrent entry sets.

It does not read category states, raw prices, earlier P1 results, ETF or Shadow
data, execution data, Web files, credentials, or network services. Any mismatch
fails before publication.

## 4. Event Construction

Each stream is scanned from common index 0 through 3283. An event starts only on
`INACTIVE + ENTRY_CANDIDATE -> ACTIVE`. The first later
`ACTIVE + EXIT_CANDIDATE -> INACTIVE` closes it. A stream still active at the
sample end produces one `OPEN` event without a forced exit.

`BLOCKED` and `HOLD_CANDIDATE` observations remain inside an active event and
are counted separately. They do not split, close, or create events. Re-entry
after a close creates a new event and is never merged with the previous event.

Each stream numbers events independently from one. IDs use
`{profile_id}__{style_unit}__{sequence_number:04d}`. The global event order is
profile order, style order, then sequence number.

## 5. Event Facts

Every event contains exactly the fields frozen in
`STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1.md`.

For `CLOSED`, the end and last-observation fields identify the first exit date.
For `OPEN`, end fields are null and last observation is common index 3283,
2026-07-15. Observation counts include both interval endpoints. Blocked and hold
counts are calculated over the complete interval.

## 6. Outputs

The command atomically replaces `data/strategy_style_logic_events_v1/` with
exactly:

- `manifest.json`
- `events.json`

`events.json` records input references, fixed axes and orders, total/closed/open
counts, and the event array. It does not copy the date axis or daily-logic arrays.

The manifest records all permitted source hashes, both contract hashes, the
event output hash and byte count, deterministic counts, and downstream status
boundaries.

## 7. Reproducibility and Publication

JSON is UTF-8 with sorted keys, no non-finite values, and one trailing newline.
Identical inputs produce identical bytes. Both outputs are staged and validated
on the same filesystem before replacing the complete directory. A failed build
or replacement preserves the prior complete output.

## 8. Status Boundary

```text
Daily logic state machine status: IMPLEMENTED
Event construction implementation status: IMPLEMENTED
Event dataset status: BUILT
Forward outcome status: NOT_COMPUTED
Walk-forward status: NOT_RUN
Parameter profile selection status: NOT_RUN
Allocation status: NOT_DEFINED
Backtest status: NOT_RUN
Integration status: DO_NOT_INTEGRATE
```

