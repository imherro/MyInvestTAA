# Strategy-Style Daily Logic Artifact V1

## 1. Purpose

This artifact applies the frozen strategy-style entry, exit, and conflict rules
to the qualified daily category states. Each parameter profile and style unit
maintains an independent `INACTIVE` or `ACTIVE` logical state and emits one
daily candidate result.

The output is logic data, not a portfolio or trading instruction. It does not
construct events, merge candidate runs, calculate forward returns, select a
profile, allocate capital, create positions, run a backtest, or change
`CURRENT_TAA`.

## 2. Formal Command

```powershell
python scripts/build_strategy_style_daily_logic.py --as-of 2026-07-15
```

The as-of date is required and frozen. Any other date fails closed. The builder
is offline and does not read credentials, raw price stores, ETF mappings,
Shadow or execution outputs, Web files, or prior P1 results.

## 3. Formal Inputs

The builder reads only the P2-Task-07 manifest, common panel, category states,
and the five contracts already named in the source manifest. Before evaluation
it validates source status, paths, SHA-256 values, byte counts, date boundaries,
profile and style order, style membership, state enumerations, array lengths,
and the current state-machine contract hash.

The three formal data inputs are referenced in the new manifest. Category
arrays are not copied into the daily-logic output.

## 4. State Machine

Every profile and style starts `INACTIVE` on the first common date. On later
dates, the prior day's `state_after` becomes the current `state_before`.

Evaluation priority is:

1. `BLOCKED`
2. `EXIT_CANDIDATE`
3. `ENTRY_CANDIDATE`
4. `HOLD_CANDIDATE`
5. `NO_CHANGE`

Unavailable required evidence produces `BLOCKED` and preserves the logical
state. An `INACTIVE` style can only enter or remain unchanged. An `ACTIVE` style
can only exit or hold. Entry changes the state to `ACTIVE`; exit changes it to
`INACTIVE`.

Growth requires pressure, both stabilization categories, and no adverse
continuation. Value and cash flow require pressure, at least one stabilization
category, and no adverse continuation. Dividend uses the value rule plus
member agreement. Dividend conflict prevents entry and forces exit when active.

All exits follow the preregistered rules: adverse continuation, loss of pressure
qualification, loss of both stabilization categories, or dividend conflict.

## 5. Concurrent Candidates

Each profile has one `concurrent_entry_candidate_set` per common date. It lists
every style that emits `ENTRY_CANDIDATE`, in the fixed order `growth`, `value`,
`dividend`, `cash_flow`. The set does not rank candidates, select a winner,
assign weights, or move capital.

## 6. Outputs

The command atomically replaces `data/strategy_style_daily_logic_v1/` with
exactly:

- `manifest.json`
- `daily_logic.json`

`daily_logic.json` references the common date axis through the fixed string
`common_panel.dates`. For every profile and style it stores `state_before`,
`daily_result`, and `state_after`, each with 3,284 entries.

The manifest records the formal source hashes, state-machine contract hash,
daily-logic output hash and byte count, invariant counts, and the boundary that
events, allocation, backtesting, and integration remain unimplemented.

## 7. Reproducibility and Publication

JSON uses UTF-8, fixed key ordering, no non-finite numbers, and one trailing
newline. Identical inputs produce identical bytes. Both files are staged and
validated on the same filesystem before the complete output directory is
replaced. A failed build or replacement preserves the prior complete output.

## 8. Status Boundary

```text
Common panel status: BUILT
Category calculation status: IMPLEMENTED
Parameter selection status: NOT_RUN
Entry/exit state machine status: IMPLEMENTED
Event status: NOT_BUILT
Walk-forward status: NOT_RUN
Allocation status: NOT_DEFINED
Backtest status: NOT_RUN
Integration status: DO_NOT_INTEGRATE
```

