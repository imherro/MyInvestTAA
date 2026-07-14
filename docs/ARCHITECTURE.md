# MyInvestTAA Architecture

## Product layers

MyInvestTAA separates research evidence, model output, execution validation, and user review.

1. **Research index layer** uses long-history index or total-return data to test allocation logic.
2. **V11 layer** produces the current offline allocation for the formal production-candidate model.
3. **ETF execution layer** maps research assets to real ETF proxies and measures execution gaps.
4. **Execution-Aware Shadow** converts the latest research weights into eligible ETF weights and cash. It remains experimental.
5. **Current Decision** displays V11 and Shadow side by side for human review. It does not merge or automatically select them.
6. **Release layer** hashes local inputs, rebuilds deterministic snapshots, runs system acceptance, and publishes a read-only release.

## User-facing pages

The global navigation contains only: System Home, Current Decision, V11 Allocation, Research and Execution Validation, and System Status. Historical diagnostic pages remain accessible only as advanced or audit routes when required by builders, tests, or governance evidence.

## Production boundary

V11 is a formal candidate model, but `production_actionable=false`. Research is not an execution portfolio. Shadow is not production approved. The Web and APIs are read-only and never generate orders, quantities, shares, target prices, or buy/sell actions.

## Offline dependency graph

The release order is preflight, Strategy Diagnosis evidence, V11 snapshot, Research validation, Execution validation, approval integrity, Shadow validation, Current Decision, system acceptance, then release manifest. Existing historical reports that cannot be safely recomputed without changing the evidence date are classified as verified local inputs instead of being silently regenerated.
