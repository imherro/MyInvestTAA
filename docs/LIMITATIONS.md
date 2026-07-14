# Limitations

## Current nonblocking conditions

- Execution Validation remains false because tradable coverage and untradable-month thresholds are not met.
- Current Decision is complete enough for human review but is not production actionable.
- The existing Starlette/httpx deprecation warning remains.

## How to interpret 40% CASH

Shadow cash includes the Research model's own cash plus weights that cannot be mapped to a sufficiently approved, price-verified ETF. It is therefore not a pure bearish market view.

## Mapping quality

The 931743 research asset currently uses a medium-quality semiconductor ETF proxy. The proxy is thematically related but broader than the research index and is not a direct tracker. This limitation is disclosed rather than hidden or upgraded automatically.

## Data timing

Market and ETF data are local offline snapshots, not real-time quotes. A passed release proves consistency with those inputs, not freshness beyond the stated as-of date.

## Not a trading instruction

The system does not place orders, calculate quantities or shares, supply target prices, select between V11 and Shadow automatically, or create a merged portfolio. No protected strategy, mapping approval, or execution gate may be changed merely to obtain a green acceptance result.
