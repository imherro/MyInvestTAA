# Strategy-Style Category State Artifact V1

## 1. Purpose

This artifact is the first deterministic calculation output for the independent
strategy-style research line. It converts the five qualified total-return index
series into one common observation panel and calculates the four preregistered
evidence categories for the three frozen parameter profiles.

It does not build entry, hold, or exit events; select a profile; create a
portfolio; run a backtest; or change `CURRENT_TAA`. It is an offline research
artifact and must not be used as an execution input.

## 2. Formal Command

```powershell
python scripts/build_strategy_style_category_states.py --as-of 2026-07-15
```

The date is mandatory and frozen. Any other date fails closed. The command does
not read `.env`, credentials, network services, `CURRENT_TAA`, ETF mappings,
Shadow outputs, execution outputs, Web files, or the retired P1 research line.

## 3. Inputs

The builder accepts only the frozen universe, qualified strategy-style source
dataset, qualification report, and the five P2 research contracts recorded in
the generated manifest. Every source file is checked by SHA-256 before any
calculation starts. Identity, order, style membership, return basis, as-of date,
qualification status, common-date completeness, and the exact 3,284-session
common window are also validated.

## 4. Outputs

The command replaces
`data/strategy_style_category_calculations_v1/` as one complete unit containing
exactly:

- `manifest.json`
- `common_panel.json`
- `category_states.json`

`common_panel.json` contains the 3,284-session date axis and five columnar member
histories: close, daily total return, normalized level, cumulative total return,
running peak, and drawdown. The first observation is normalized to 1.0, with a
null daily return, zero cumulative return, peak 1.0, and zero drawdown.

`category_states.json` contains profiles `PROFILE_A`, `PROFILE_B`, and
`PROFILE_C` in fixed order. Each
profile stores its indivisible parameter set, member-level intermediate values,
member category states, four style-unit states, dividend-member agreement, and
dates on which each calculation first becomes available. Null represents an
unavailable numeric value; state arrays use only the enumerations declared in
the file.

## 5. Calculation Rules

The implementation follows
`STRATEGY_STYLE_CATEGORY_CALCULATION_PREREGISTRATION_V1.md` exactly:

- pressure is met at or below the profile drawdown threshold;
- absolute stabilization is met when the own horizon return is non-negative;
- relative stabilization is met when the own horizon return is not below the
  median return of the other four members;
- adverse continuation is met only when the current normalized level is
  strictly below the minimum of the preceding lookback window, excluding the
  current observation;
- both dividend members must meet a positive category for the dividend style to
  meet it, while either member meeting adverse continuation makes the dividend
  style meet that risk category;
- dividend agreement requires all four member-category states to match.

No calculation uses observations before the common start or after the current
date. Comparisons use full stored floating-point values without display rounding.

## 6. Reproducibility and Publication

JSON is serialized with fixed key ordering, UTF-8 encoding, one trailing newline,
and non-finite numbers disabled. Identical inputs therefore produce identical
bytes. The manifest records every formal input and contract hash plus the hash
and byte count of both calculated outputs.

All three files are written and validated in a staging directory on the same
filesystem. Only a complete valid set replaces the prior directory. A failed
build or replacement leaves the previous complete artifact set intact.

## 7. Status Boundary

```text
Common panel status: BUILT
Category calculation implementation status: IMPLEMENTED
Parameter selection status: NOT_RUN
Entry/exit state machine status: NOT_APPLIED
Event status: NOT_BUILT
Walk-forward status: NOT_RUN
Allocation status: NOT_DEFINED
Backtest status: NOT_RUN
Integration status: DO_NOT_INTEGRATE
```
