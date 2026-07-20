# Unified Strategy-Style Observation Data Contract V1

## 1. 目的与范围

本文为 `Strategy-Style Drawdown Rebalancing`（策略风格回撤再平衡）的四个风格决策单元定义统一、无前视、可复核的数据观察口径。

本合同只确定正式数据快照、共同日期区间、每日观察的可用时间、五项指数到四个观察单元的映射、允许保留的确定性字段，以及红利双指数在观察层的表达方式。

本合同不定义回撤阈值、分位数、移动窗口、趋势或动量指标、波动率指标、相对强弱规则、排名、估值确认、进入规则、退出规则、冲突规则、事件、walk-forward、仓位或回测。

## 2. 正式数据来源

观察合同只能引用 P2-Task-01 建立的独立数据边界：

- `config/strategy_style_research_universe_v1.json`
- `data/strategy_style_research/manifest.json`
- `data/strategy_style_research/sse_trade_calendar.json`
- `data/strategy_style_research/prices/CN2296_CNI.json`
- `data/strategy_style_research/prices/CN2371_CNI.json`
- `data/strategy_style_research/prices/H00015_CSI.json`
- `data/strategy_style_research/prices/H00922_CSI.json`
- `data/strategy_style_research/prices/480092_CNI.json`
- `reports/strategy_research/strategy_style_data_qualification_v1.json`

固定数据版本为：

```text
dataset_id: STRATEGY_STYLE_RESEARCH_DATASET_V1
as_of_date: 2026-07-15
qualification: QUALIFIED
```

不得读取或引用 `data/research_prices/`、`data/market/`、`reports/current/`、`CURRENT_TAA` 月度配置、ETF 或执行数据，也不得引用旧回撤研究报告中的事件或阈值。

## 3. 三层边界

### 3.1 数据源层

数据源层只包含 Tushare 全收益指数的以下字段：

```text
date
close
return_basis
```

### 3.2 观察层

观察层只允许对正式源数据进行无可调参数、完全确定性的转换。它不得判断买入或卖出、是否触发、风格是否便宜、趋势是否稳定，不得产生排名，也不得产生通过或失败结论。

### 3.3 信号层

包含以下任一内容的计算均属于后续信号层，本合同不得定义：窗口长度、阈值、分位数、均值或中位数区间、移动平均、波动率估计、z-score、排名、相对强弱判断、趋势确认、反转确认、估值确认、进入或退出状态。

## 4. 统一时间轴

### 4.1 共同观察起点

四风格统一比较只能从所有五项指数均具备数据的首个 SSE 开放日开始：

```text
common_observation_start: 2013-01-04
```

创成长R的首日是 2013-01-04，其余四项指数在该日已具备数据。不得使用成长风格尚不存在期间的数据构建跨风格比较。

### 4.2 共同观察终点

```text
common_observation_end: 2026-07-15
```

### 4.3 共同日期集合

共同日期集合只能来自 `data/strategy_style_research/sse_trade_calendar.json`，过滤条件为：

```text
2013-01-04 <= date <= 2026-07-15
```

当前 V1 必须恰好包含 3284 个 SSE 开放交易日。

### 4.4 完整性

五项指数在共同日期集合中的每个日期均必须有且只有一条价格。不允许缺失、额外日期、前向填充、后向填充、插值，也不允许删除某日后继续研究。

任一指数无法形成完整共同面板时，观察状态必须为 `BLOCKED`。不得通过缩短个别风格的日期范围继续。

## 5. 观察可用时间

日期为 `t` 的观察只能在该交易日收盘后视为已知：

```text
observation_date = t
available_after = market close on t
earliest_decision_use = next SSE open session after t
```

本合同不定义交易或调仓执行规则，但禁止在当日收盘前使用当日 `close`，禁止用未来日期修正历史观察，禁止用完整样本统计量反向计算历史观察，禁止使用 2026-07-15 之后的数据。

## 6. 五项指数与四个观察单元

固定映射如下：

| style bundle | member asset | 正式名称 |
| --- | --- | --- |
| growth | `CN2296.CNI` | 创成长R |
| value | `CN2371.CNI` | 国证价值R |
| dividend | `H00015.CSI` | 红利收益 |
| dividend | `H00922.CSI` | 中红收益 |
| cash_flow | `480092.CNI` | 国证自由现金流指数R |

每个共同日期形成 5 条 `member observations` 和 4 个 `style observation bundles`：growth、value、cash_flow 各含 1 条 member，dividend 含 2 条 members。观察层不得把五项指数误写成五个风格。

## 7. 统一 member 观察字段

### 7.1 身份字段

```text
date
style_unit
asset_id
display_name
return_basis
```

固定要求为 `return_basis = total_return`。

### 7.2 原始字段

```text
close
```

`close` 必须有限、严格大于 0、来自正式独立价格文件，且不做复权或二次调整。

### 7.3 单日全收益率

```text
daily_total_return_t = close_t / close_(t-1) - 1
```

其中 `t-1` 是共同日期集合中的前一个 SSE 开放日。共同观察首日固定为：

```text
daily_total_return = null
```

不得使用 2013-01-04 之前的数据计算首日收益，以保证所有风格采用完全相同的共同观察边界。

### 7.4 标准化全收益水平

共同首日固定为：

```text
normalized_level = 1.0
```

后续定义为：

```text
normalized_level_t = close_t / close_on_2013_01_04
```

该字段只用于使不同点位尺度的指数可视化和比较，不代表得分或排名。

### 7.5 共同样本累计收益

```text
cumulative_total_return_t = normalized_level_t - 1
```

### 7.6 共同样本运行峰值

```text
running_peak_level_t = max(normalized_level_s) for all common observation dates s <= t
```

运行峰值只使用共同起点以来的数据，必须单调不下降，不得使用各指数在 2013 年以前的历史高点。

### 7.7 当前回撤

```text
drawdown_t = normalized_level_t / running_peak_level_t - 1
drawdown_t <= 0
```

达到新高时 `drawdown_t = 0`。该字段只是连续观察事实，不构成回撤事件、回撤等级、触发状态、增配资格或退出状态。

## 8. 红利双指数观察口径

### 8.1 保留两条 member 序列

红利 observation bundle 必须同时保留 `H00015.CSI member observation` 和 `H00922.CSI member observation`。两者分别完整计算：

```text
close
daily_total_return
normalized_level
cumulative_total_return
running_peak_level
drawdown
```

### 8.2 不产生红利合成序列

观察层禁止定义两指数平均、等权组合、几何平均、取最小或最大回撤、任一指数优先、多数投票、任一指数触发即视为红利触发、两指数同时满足才触发，或选择历史表现更好的指数。

因此当前不存在：

```text
dividend_composite_close
dividend_composite_return
dividend_composite_drawdown
dividend_signal
```

后续预注册信号类别时，必须在查看相关结果前决定如何使用两条红利证据。

### 8.3 不双重计算

即使每天存在两条红利 member observations，也只能形成一个 `dividend style observation bundle`，不得形成两个红利风险单元。

## 9. 跨风格比较边界

本合同只允许将四个 style bundles 放在相同日期和字段语义下观察，不定义四风格平均指数、四风格基准组合、风格相对比率、横截面排名、最强或最弱风格、相对趋势、相对动量或风格轮动分数。这些均属于后续信号层。

统一观察口径不等于统一信号规则，也不代表四类风格未来必须使用完全相同的确认条件。

## 10. 原生历史的处理

P2-Task-01 保留了各指数早于 2013-01-04 的原生历史。原生历史继续保留在数据集，不删除或截断源文件，可用于数据质量检查和背景描述，但不得进入四风格统一比较，也不得影响共同面板的标准化水平、运行峰值或回撤。

后续任何跨风格候选必须使用从 2013-01-04 开始的共同面板。不得为价值或红利使用更长历史，同时为成长使用较短历史，再将结果直接横向比较。

## 11. 确定性不变量

```text
common dates are identical for all five members
member row count per common date = 5
style bundle count per common date = 4
dividend member count per common date = 2
all other style member counts per common date = 1
common session count = 3284
member-date observation count = 16420
```

不得增加现金、宽基、主题、行业或资源观察行。

## 12. 数据异常状态

观察合同只允许 `DEFINED_FOR_REVIEW` 和 `BLOCKED` 两种整体状态。出现以下任一情况必须为 `BLOCKED`：

- 来源资格报告不是 `QUALIFIED`；
- manifest 或价格 SHA 不匹配；
- 五项身份与固定映射不一致；
- 共同日期少于 3284；
- 任一共同日期缺少 member；
- 任一日期出现重复 member；
- `close` 无效；
- `return_basis` 不是 `total_return`；
- 日期晚于正式截止日；
- 使用正式 `CURRENT_TAA` 或其他缓存补数据；
- 产生未经预注册的红利合成序列。

本合同不生成实际异常报告。

## 13. 与机制合同的关系

本合同引用 [STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md](STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md)，只落实冻结研究顺序中的第 2 步，不改变机制合同，也不定义任何候选信号。

回撤字段只是观察事实，回撤仍然不是充分条件。总权益和风格袖套预算约束尚未进入任何计算实现。

## 14. 后续顺序

下一步只能是“预注册候选信号类别”，不能选择信号参数、构建事件、运行 walk-forward、设计仓位、回测或集成 `CURRENT_TAA`。候选信号类别通过后，才可进入进入、退出和冲突处理规则的预注册。

## 15. 当前状态

```text
Observation contract status: DEFINED_FOR_REVIEW
Source dataset status: QUALIFIED
Common panel status: DEFINED_NOT_BUILT
Signal category status: NOT_DEFINED
Entry and exit status: NOT_DEFINED
Event status: NOT_BUILT
Walk-forward status: NOT_RUN
Allocation status: NOT_DEFINED
Integration status: DO_NOT_INTEGRATE
```
