# Drawdown Add-On Research Decision V1

## Status

- Decision: REJECTED
- Integration status: DO_NOT_INTEGRATE
- Parameter tuning status: CLOSED

## Fixed Rule Tested

- Threshold family: `completed_event_depth_quantile`
- Tiers: `p75 / p90 / p95`
- Base weight: 70% index / 30% cash
- Tier 1 weight: 80% index / 20% cash
- Tier 2 weight: 90% index / 10% cash
- Tier 3 weight: 100% index / 0% cash
- Peak recovery weight: 70% index / 30% cash
- Transaction cost: 10 bps one way
- Execution: next trading-day close

## Source Commits

- P1-Task-09 candidate: `8c8914e06259799e38be43dc6235d34854a52ac7`
- P1-Task-10 source: `778b33d3163b722c665bbb4ae848b10b5b6acdb6`
- P1-Task-10 report: `58ecd2f236e960e994a359c3d718e8b643f99952`

## Falsification Result

The values below are copied directly from
`reports/strategy_research/drawdown_addon_candidate_backtest_v1.json`. They
are not recomputed in this decision record.

| Asset | Strategy Calmar | Static 70/30 Calmar | MDD difference vs 70/30 | Excess total return vs 70/30 |
| --- | ---: | ---: | ---: | ---: |
| CSI 300 Total Return | 0.10085566804487121 | 0.10591466238462158 | -0.07291237753589153 | 0.14570315832083325 |
| CSI 500 Total Return | 0.057534284131641814 | 0.06564856352361112 | -0.08593958476115127 | 0.013009237996724377 |
| CSI 1000 Total Return | 0.03374137985592749 | 0.044147485193423625 | -0.0821053789219961 | -0.07999667611175121 |
| CSI Dividend Total Return | 0.15479331410464478 | 0.16489726850422212 | -0.05826402540875608 | 0.18730254075116903 |
| CNI Free Cash Flow Total Return | 0.2979791327138935 | 0.32772148450915606 | -0.05311892908786442 | 0.19303386890888863 |

All five strategy Calmar ratios are below their static 70/30 benchmarks, and
all five maximum drawdowns are worse than the 70/30 benchmarks. CSI 1000 also
has a lower total return. For the other four assets, the extra return does not
compensate for the additional drawdown and volatility.

The strategy remains at 100% index weight for much of each test period. It
therefore approaches buy-and-hold risk after a deep drawdown while delivering
less total return than buy and hold for all five assets.

## Decision

The candidate failed its pre-registered risk-adjusted performance test. It will
not be integrated into CURRENT_TAA, ETF, Shadow, execution, release, or Web.

## No Post-Hoc Optimization

The following changes must not be made in response to these results:

- Adjusting the `p75 / p90 / p95` thresholds
- Adjusting the `70% / 80% / 90% / 100%` weights
- Adjusting transaction costs
- Adding stop-loss, take-profit, or new recovery rules
- Selecting different parameters by asset
- Retaining only the better-performing assets
- Running a parameter search for this candidate

Any future drawdown add-on research must propose a different economic
mechanism, pre-register it before viewing new results, and create an independent
candidate. This sample must not be used to optimize the new candidate.

## Retained Negative Evidence

The following reports are retained as negative research evidence and are not
formal system inputs:

- `reports/strategy_research/drawdown_threshold_evidence_table.json`
- `reports/strategy_research/drawdown_addon_trigger_candidate_v1.json`
- `reports/strategy_research/drawdown_addon_candidate_backtest_v1.json`
