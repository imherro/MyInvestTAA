# Limitations

## Current nonblocking conditions

- Execution Validation remains false because tradable coverage and untradable-month thresholds are not met.
- Current Decision is complete enough for human review but is not production actionable.
- The existing Starlette/httpx deprecation warning remains.

The binary untradable-month metric is intentionally strict: any execution gap marks the month. Use the continuous gap-weight metrics to judge severity, but do not treat them as a replacement for the existing gate.

Non-executable assets are not synonymous with assets that lack an ETF. Reports separately identify assets with no approved proxy and assets whose only available proxy is excluded for low mapping quality.

## How to interpret 40% CASH

Shadow cash includes the Research model's own cash plus weights that cannot be mapped to a sufficiently approved, price-verified ETF. It is therefore not a pure bearish market view.

## Mapping quality

The 931743 research asset currently uses a medium-quality semiconductor ETF proxy. The proxy is thematically related but broader than the research index and is not a direct tracker. This limitation is disclosed rather than hidden or upgraded automatically.

## Data timing

Market and ETF data are local offline snapshots, not real-time quotes. A passed release proves consistency with those inputs, not freshness beyond the stated as-of date.

Counterfactual mapping results are configuration-specific. The system marks mutable evidence historical-only whenever any required input is missing, damaged, or no longer matches the analysis contract. Only a fully verified counterfactual enters the committed release. The formal API additionally verifies the whole release directory and returns unavailable on any release-level integrity failure; it never falls back to mutable evidence. Counterfactual evidence still cannot authorize a mapping change.

## Experimental Execution Engine V2 B1

Execution Engine V2 B1 is an independent research experiment. It does not replace the formal V1 report, enter Current Decision, alter mapping approvals, or participate in formal release acceptance.

- The official local China-equity trade calendar is retained without taking a global intersection of ETF price dates.
- Each ETF becomes eligible independently. In B1, the verified exchange listing date is used as the investable start date; this does not prove minimum liquidity or implementation capacity.
- An unheld ETF with no price cannot be entered and its target weight remains cash. A held ETF with no current price is valued at its last verified price, contributes zero return for that day, and cannot be traded.
- Signals execute no earlier than the next local trading day. B1 assumes zero commission, zero slippage, and zero cash yield.
- Results are experimental attribution evidence only and never produce orders, shares, quantities, amounts, or target prices.

## Not a trading instruction

The system does not place orders, calculate quantities or shares, supply target prices, select between V11 and Shadow automatically, or create a merged portfolio. No protected strategy, mapping approval, or execution gate may be changed merely to obtain a green acceptance result.
