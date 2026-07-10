# MyInvestTAA Research Universe Design

Status: design consensus after ChatGPT review on 2026-07-10.

## 1. Background

MyInvestTAA is a tactical asset allocation research system. Its goal is not high-frequency trading or single-stock speculation. The system adjusts asset weights around a strategic allocation baseline according to asset risk, trend, drawdown, theme strength, market regime, and execution feasibility.

The early project used ETFs as the main research assets. As the project moves into real market research, the system must separate:

- Research objects: assets, styles, themes, sectors, and risk exposures.
- Execution tools: ETFs, funds, and other tradable products.

Future MyInvestTAA research should therefore move from ETF ranking to Research Asset Ranking. ETFs remain important, but as execution proxies rather than the primary research assets.

## 2. Core Principles

### 2.1 Prefer Indices For Research Assets

TAA research studies asset exposure, not ETF product behavior.

Research assets should prefer these return bases, in order:

1. Official total return index: `return_basis=total_return`.
2. Official net return index: `return_basis=net_return`.
3. Price index: `return_basis=price_index`, mainly for monitoring or clearly flagged research gaps.
4. ETF adjusted price or adjusted NAV: mainly for execution validation.

`net_return` must not be silently mixed with `total_return` in the same ranking pool. It can be used only when explicitly marked and enabled by configuration.

### 2.2 ETFs Are Execution Proxies

ETFs contain product-level noise:

- Late inception dates.
- Shorter available history.
- Management and custody fees.
- Tracking error.
- Premium and discount.
- Liquidity changes.
- Scale changes.
- Creation, redemption, and turnover effects.

Therefore, ETFs should not be the main research-layer assets. They should answer execution questions:

- Is there a tradable product?
- Does the ETF track the research asset well after inception?
- Are volume and liquidity sufficient?
- Does the strategy remain useful after execution discounts?

### 2.3 Do Not Create Pseudo Long ETF Histories

The system must not splice index history and ETF history into one fake long ETF curve.

Incorrect:

- 2010-2019: use index history.
- 2020-2026: use ETF history.
- Merge the result as a long ETF history.

Correct:

- Research Backtest: use indices or total return indices over the long available history.
- Execution Backtest: use adjusted ETF prices only from ETF inception or tradable start date.

Reports must show the two results separately.

## 3. Architecture

```text
Research Asset Layer
    |
    v
Research Backtest
    |
    v
Signal / Ranking / Allocation
    |
    v
Execution Mapping Layer
    |
    v
Execution Backtest
    |
    v
Execution Feasibility / Discount
    |
    v
Production Governance
```

### 3.1 Research Asset Layer

The research asset layer handles:

- Long-term return and drawdown research.
- Signal calculation.
- TAA ranking.
- Research backtests.
- Asset rotation decisions.

Example research assets:

- `H00300.CSI` 沪深300收益.
- `H00905.CSI` 中证500收益.
- `H00852.CSI` 中证1000全收益.
- `399606.SZ` 创业板R.
- `000688CNY01.CSI` 科创50全收益.
- `H00015.CSI` 红利收益.
- `H20007.CSI` 芯片产业全收益.
- `H21152.CSI` CS创新药全收益.
- `H00805.CSI` A股资源全收益.

### 3.2 Execution Asset Layer

The execution asset layer handles:

- ETF tradability validation.
- ETF inception and investable date limits.
- Adjusted price validation.
- Execution discounts.
- Trading constraints.
- Execution backtests.

Example execution proxies:

- 沪深300ETF.
- 中证500ETF.
- 创业板ETF.
- 半导体ETF.
- 黄金ETF.
- 国债ETF.

### 3.3 Mapping Layer

The mapping layer connects research assets to execution tools. One research asset can map to multiple execution proxies.

```json
{
  "research_asset_id": "H20007.CSI",
  "primary_execution_proxy": "512760.SH",
  "execution_proxies": ["512760.SH", "159995.SZ"]
}
```

## 4. File Structure

New core files:

```text
data/universe/china_research_universe.json
data/universe/china_execution_universe.json
data/universe/asset_mapping.json
```

Compatibility file:

```text
data/universe/china_etf_universe.json
```

`china_etf_universe.json` can remain for compatibility, but future research engines should not treat it as the primary asset pool.

## 5. Research Universe Schema

Each `china_research_universe.json` item should include at least:

```json
{
  "asset_id": "H00300.CSI",
  "name": "沪深300收益",
  "instrument_type": "index",
  "role": "research",
  "category": "broad_base",
  "sleeve": "equity_core",
  "provider": "tushare",
  "data_api": "index_daily",
  "return_basis": "total_return",
  "data_start_date": "2005-01-01",
  "investable_start_date": "2005-01-01",
  "eligible_for_allocation": true,
  "notes": "官方收益指数，优先用于研究回测"
}
```

Required fields:

| Field | Meaning |
| --- | --- |
| `asset_id` | Research asset code. |
| `name` | Asset name. |
| `instrument_type` | `index`, `sw_index`, `synthetic`, or `monitor`. |
| `role` | `research` or `monitor`. |
| `category` | `broad_base`, `dividend`, `theme`, `resource`, `industry`, or `defensive`. |
| `sleeve` | Portfolio sleeve. |
| `provider` | `tushare`, `baostock`, `manual`, or `other`. |
| `data_api` | `index_daily`, `sw_daily`, `fund_daily`, or `custom`. |
| `return_basis` | `total_return`, `net_return`, `price_index`, `qfq`, or `hfq`. |
| `data_start_date` | Earliest available data date. |
| `investable_start_date` | First date usable for research backtests or allocation. |
| `eligible_for_allocation` | Whether the asset can enter the main TAA allocation. |
| `notes` | Return basis and data caveats. |

`data_start_date` and `investable_start_date` must be separate. For indices they may be the same. For ETFs, `investable_start_date` should reflect ETF inception or tradable start date.

## 6. Execution Universe Schema

Each `china_execution_universe.json` item should include at least:

```json
{
  "asset_id": "510300.SH",
  "name": "沪深300ETF",
  "instrument_type": "etf",
  "role": "execution",
  "provider": "tushare",
  "data_api": "fund_daily",
  "return_basis": "qfq",
  "data_start_date": "2012-05-28",
  "investable_start_date": "2012-05-28",
  "management_fee": null,
  "tracking_error": null,
  "liquidity_score": null,
  "notes": "执行代理，不能用于ETF成立日前回测"
}
```

Phase 1 execution fields:

- ETF code.
- ETF name.
- Research asset mapping.
- ETF inception date.
- Adjustment basis.
- Tradable start date.
- Non-tradable interval markers.

Phase 2 execution fields:

- Scale.
- Turnover or amount.
- Bid-ask spread.
- Management fee.
- Tracking error.
- Liquidity score.
- Execution discount.

## 7. Asset Mapping Schema

Example `asset_mapping.json` item:

```json
{
  "research_asset_id": "H00300.CSI",
  "research_asset_name": "沪深300收益",
  "primary_execution_proxy": "510300.SH",
  "execution_proxies": ["510300.SH", "159919.SZ"],
  "mapping_quality": "high",
  "notes": "宽基ETF代理充足"
}
```

| Field | Meaning |
| --- | --- |
| `research_asset_id` | Research asset code. |
| `research_asset_name` | Research asset name. |
| `primary_execution_proxy` | Default ETF execution proxy. |
| `execution_proxies` | Alternative execution proxies. |
| `mapping_quality` | `high`, `medium`, `low`, or `none`. |
| `notes` | Mapping notes and caveats. |

## 8. Initial Research Asset Pool

### 8.1 Broad Base

| Asset | Code | Return Basis |
| --- | --- | --- |
| 沪深300收益 | `H00300.CSI` | `total_return` |
| 中证500收益 | `H00905.CSI` | `total_return` |
| 中证1000全收益 | `H00852.CSI` | `total_return` |
| 创业板R | `399606.SZ` | `total_return` or official return index |
| 科创50全收益 | `000688CNY01.CSI` | `total_return` |

### 8.2 Dividend

| Asset | Code | Return Basis |
| --- | --- | --- |
| 红利收益 | `H00015.CSI` | `total_return` |
| 中红收益 | `H00922.CSI` | `total_return` |

### 8.3 Hot Themes

| Asset | Code | Return Basis |
| --- | --- | --- |
| 芯片产业全收益 | `H20007.CSI` | `total_return` |
| 半导体材料设备全收益 | `931743CNY010.CSI` | `total_return` |
| CS创新药全收益 | `H21152.CSI` | `total_return` |
| 机器人全收益 | `H20590.CSI` | `total_return` |
| CS新能源全收益 | `H20771.CSI` | `total_return` |
| 中证算力全收益 | `931688CNY010.CSI` | `total_return` |

### 8.4 Resource And Cycle

| Asset | Code | Return Basis |
| --- | --- | --- |
| A股资源全收益 | `H00805.CSI` | `total_return` |

### 8.5 Shenwan Industry Monitor

Shenwan industry indices enter `industry_monitor` in Phase 1 and do not enter the main TAA allocation.

| Industry | Code | Return Basis |
| --- | --- | --- |
| 食品饮料 | `801120.SI` | `price_index` |
| 医药生物 | `801150.SI` | `price_index` |
| 电子 | `801080.SI` | `price_index` |
| 电力设备 | `801730.SI` | `price_index` |
| 计算机 | `801750.SI` | `price_index` |
| 通信 | `801770.SI` | `price_index` |
| 传媒 | `801760.SI` | `price_index` |
| 公用事业 | `801160.SI` | `price_index` |
| 有色金属 | `801050.SI` | `price_index` |
| 煤炭 | `801950.SI` | `price_index` |
| 银行 | `801780.SI` | `price_index` |
| 非银金融 | `801790.SI` | `price_index` |
| 房地产 | `801180.SI` | `price_index` |
| 汽车 | `801880.SI` | `price_index` |
| 国防军工 | `801740.SI` | `price_index` |
| 机械设备 | `801890.SI` | `price_index` |
| 建筑材料 | `801710.SI` | `price_index` |
| 建筑装饰 | `801720.SI` | `price_index` |

If Shenwan industry data is available only as price indices, reports must warn:

> This index is a price index and does not include dividend reinvestment. Long-term returns may be understated, especially for high-dividend industries such as banks, coal, and utilities.

## 9. Data API Routing

Provider logic must route by asset type and `data_api`.

| Asset Type | `data_api` | Purpose |
| --- | --- | --- |
| CSI / exchange index / total return index | `index_daily` | Main research assets. |
| Shenwan industry index | `sw_daily` | Industry monitor. |
| ETF | `fund_daily` | Execution proxy. |
| ETF adjustment factor | `fund_adj` | `qfq` / `hfq` execution returns. |
| Stock daily | `daily` | Stock breadth and theme confirmation. |

The provider layer must not assume all assets are ETFs.

Candidate APIs:

- `get_research_history(asset)`.
- `get_execution_history(asset)`.
- `get_industry_history(asset)`.

Alternatively, route inside `get_price_history()` based on `data_api`.

## 10. Backtest Output

Reports must include both research and execution results.

### 10.1 Research Backtest

Inputs:

- `china_research_universe.json`.
- Official total return indices where available.
- Long available history.

Questions answered:

- Does the strategy logic work?
- Does asset rotation create excess return?
- Is max drawdown controlled?

### 10.2 Execution Backtest

Inputs:

- `china_execution_universe.json`.
- Adjusted ETF prices.
- ETF inception and tradable periods.

Questions answered:

- Is the strategy executable with real ETFs?
- Does performance survive after ETF inception?
- Does the edge remain after execution discounts?

### 10.3 Execution Gap

Reports should calculate:

```text
execution_gap = research_return - execution_return
```

Possible sources:

- Tracking error.
- Management fees.
- Liquidity.
- Late ETF inception.
- Premium and discount.
- Return basis mismatch.

## 11. Risk And Execution Constraints

### 11.1 Theme Sleeve Limits

Theme assets can enter the allocation only under explicit sleeve constraints.

```json
{
  "theme_sleeve_max_weight": 20,
  "single_theme_max_weight": 10,
  "theme_count_limit": 3
}
```

### 11.2 Industry Monitor Limits

Shenwan industries are Phase 1 monitor assets only:

```json
{
  "eligible_for_allocation": false
}
```

They can be used for:

- Industry observation.
- Market explanation.
- Theme confirmation.
- Risk warnings.

They must not directly enter the main TAA portfolio in Phase 1.

### 11.3 Execution Layer Limits

The execution layer must enforce:

- ETFs are not tradable before inception.
- Assets without adjusted price data cannot enter execution backtests.
- Missing liquidity data must be marked as `liquidity_unknown`.
- `mapping_quality=low` assets must not be automatically used as production execution tools.

## 12. Web Report Requirements

### 12.1 Return Basis Display

Every asset row must display `return_basis`:

- `total_return`.
- `net_return`.
- `price_index`.
- `qfq`.
- `hfq`.

### 12.2 Data Basis Warnings

If `return_basis=price_index`, reports must warn:

> Price index data does not include dividend reinvestment. Long-term returns may be understated.

### 12.3 Dual Curves

Reports must show:

- Research Curve.
- Execution Curve.

They must not show only one synthetic curve.

### 12.4 Mapping Quality

Reports should show:

- Research asset.
- Primary execution proxy.
- Mapping quality.
- Execution start date.

## 13. Implementation Plan

### Phase 1: Research Universe Audit

Goal: build the research asset pool and data availability audit.

Tasks:

- Add `china_research_universe.json`.
- Add `china_execution_universe.json`.
- Add `asset_mapping.json`.
- Add universe validators.
- Add `data_api` routing.
- Add return basis audit report.
- Add Web page: Research Universe Audit.

Out of scope:

- Strategy optimization.
- Production strategy replacement.
- Industry rotation.

### Phase 2: Research Backtest

Goal: use research indices instead of ETFs for the main backtest.

Tasks:

- Add Research Backtest Engine.
- Add Research Performance Report.
- Compare against current ETF-based results.

### Phase 3: Execution Backtest

Goal: validate ETF execution feasibility.

Tasks:

- Add ETF proxy mapping.
- Filter by ETF inception date.
- Backtest adjusted ETF prices.
- Apply execution discounts.
- Add execution gap analysis.

### Phase 4: Industry Monitor

Goal: use Shenwan industries as explanation and monitoring, not allocation.

Tasks:

- Add Industry Monitor page.
- Add industry trend, drawdown, and return basis warnings.
- Add industry confirmation signals for theme research.

### Phase 5: Production Integration

Goal: connect Research Asset Ranking to the current production candidate.

Tasks:

- Replace production ranking input with research assets.
- Add execution mapping.
- Add dual reports.
- Re-run production governance.

## 14. Acceptance Criteria

Task-023 Phase 1 is complete only when:

- The research universe, execution universe, and mapping files exist.
- Validators reject missing `return_basis`, `data_api`, `data_start_date`, or `investable_start_date`.
- The data audit can distinguish `index_daily`, `sw_daily`, and `fund_daily`.
- Web output shows return basis and allocation eligibility.
- Shenwan industry assets are marked `eligible_for_allocation=false`.
- No pseudo long ETF curve is generated.
- Existing tests still pass.

## 15. Conclusion

MyInvestTAA should upgrade from an ETF universe to a research universe.

Final structure:

```text
Research Universe
    |
    v
Research Backtest
    |
    v
TAA Signal
    |
    v
Execution Mapping
    |
    v
Execution Backtest
    |
    v
Execution Feasibility
    |
    v
Production Governance
```

This design requires:

- No mixed return basis without explicit labels.
- No pseudo long ETF histories.
- No direct use of Shenwan price indices in the main allocation during Phase 1.
- ETFs as execution proxies only.
- Reports that show both research-layer and execution-layer results.

This is the foundation for upgrading MyInvestTAA from an ETF rotation system to a full asset allocation research system.
