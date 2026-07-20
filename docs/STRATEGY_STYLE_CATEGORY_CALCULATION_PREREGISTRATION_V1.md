# Strategy-Style Category Calculation Preregistration V1

## 1. 目的与范围

本文为已冻结的五类策略风格证据预注册确定性的计算定义和有限参数研究边界。

本文只定义四类通用证据如何从共同观察字段计算、红利两项 member 如何形成一个风格证据状态、允许研究的完整参数配置，以及参数可用性、预热期、无前视和精度规则。

本文不构建共同面板，不运行计算，不生成任何 `MET` 或 `NOT_MET` 状态及日期结果，不构建事件，不运行 walk-forward，不选择参数配置，不设计仓位，不运行回测，也不修改 `CURRENT_TAA`。

## 2. 正式上游合同

本文引用：

- [STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md](STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md)
- [STRATEGY_STYLE_OBSERVATION_DATA_CONTRACT_V1.md](STRATEGY_STYLE_OBSERVATION_DATA_CONTRACT_V1.md)
- [STRATEGY_STYLE_SIGNAL_CATEGORY_PREREGISTRATION_V1.md](STRATEGY_STYLE_SIGNAL_CATEGORY_PREREGISTRATION_V1.md)
- [STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md](STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md)

五类证据集合以及进入、退出和冲突逻辑均已冻结。本文只落实证据计算预注册，不得修改任何上游逻辑，不读取历史表现或未来收益，也不判断哪套参数配置更好。

## 3. 计算层级

所有四类通用证据先在以下 5 条 member 序列上独立计算，顺序固定：

```text
CN2296.CNI
CN2371.CNI
H00015.CSI
H00922.CSI
480092.CNI
```

growth、value、cash_flow 的唯一 member 状态直接成为风格状态。红利的两项 member 先分别计算，再按本文规则形成一个 dividend 通用类别状态和一个 `dividend_member_agreement` 状态。

不得直接对两项红利价格求平均、构造等权净值或合成全收益指数。

## 4. 共同计算原语

### 4.1 H 期全收益

对 member `m`：

```text
horizon_return_m(t, h) = close_m(t) / close_m(t-h) - 1
```

`t-h` 指共同日期集合中向前第 `h` 个 SSE 开放日，不使用自然日或共同观察起点之前的数据。不足 `h` 个先前共同交易日时返回 `UNAVAILABLE`。

### 4.2 同期 peer 收益

member `m` 的 peer 集合为另外 4 条 member 序列：

```text
peer_returns_m(t, h) = {
  horizon_return_j(t, h) for every member j != m
}
```

任一 peer 收益不可用时：

```text
peer_median_return_m(t, h) = UNAVAILABLE
```

否则：

```text
peer_median_return_m(t, h) = median(peer_returns_m(t, h))
```

peer median 是五条 member 序列之间的证据参考，不代表五个风格风险单元，不得用于排名、权重或资产选择。

### 4.3 近期新低

```text
prior_min_level_m(t, h) = min(
  normalized_level_m(s)
  for the h common sessions immediately before t
)
```

区间不包含 `t`。不足 `h` 个先前共同交易日时不可用，不得使用 2013-01-04 之前的数据。

## 5. Drawdown Pressure 计算

member 状态定义为：

```text
drawdown_pressure_m(t) = MET
if and only if:
drawdown_m(t) <= -pressure_threshold
```

否则为 `NOT_MET`。当日 drawdown 缺失或非有限数、参数配置无效、来源观察不完整时返回 `UNAVAILABLE`。边界 `drawdown = -pressure_threshold` 视为 `MET`。

不得使用 p75、p90、p95、扩展样本分位数、滚动分位数、每风格不同阈值或每 member 不同阈值。

## 6. Absolute Stabilization 计算

```text
absolute_stabilization_m(t) = MET
if and only if:
horizon_return_m(t, absolute_horizon) >= 0
```

否则为 `NOT_MET`，恰好为 0 时视为 `MET`。不足观察期或收益不可计算时返回 `UNAVAILABLE`。

该定义不使用回撤阈值或运行峰值，不把单日上涨视为稳定，不使用未来收益、移动平均或拟合趋势。

## 7. Relative Stabilization 计算

```text
relative_return_gap_m(t) =
  horizon_return_m(t, relative_horizon)
  - peer_median_return_m(t, relative_horizon)
```

```text
relative_stabilization_m(t) = MET
if and only if:
relative_return_gap_m(t) >= 0
```

否则为 `NOT_MET`，恰好为 0 时视为 `MET`。任一 member 缺少该期限收益时，当日所有 member 的 `relative_stabilization` 均为 `UNAVAILABLE`。

该计算不得生成横截面排名、选择最强风格、设置前 N 名，也不得以回撤深度参与 relative 计算或使用价值、红利的更长原生历史。peer median 只提供证据参考，不形成配置基准。

## 8. Adverse Continuation 计算

```text
adverse_continuation_m(t) = MET
if and only if:
normalized_level_m(t) < prior_min_level_m(t, adverse_lookback)
```

否则为 `NOT_MET`。当日水平与此前最低水平相等时为 `NOT_MET`；不足观察期或数据不可用时为 `UNAVAILABLE`。

该定义只判断是否继续创近期新低，不使用 drawdown 阈值、absolute return 的正负条件、relative return、波动率或未来数据。

## 9. 单 member 风格映射

growth、value 和 cash_flow 的各通用类别状态直接等于其唯一 member 状态，例如：

```text
drawdown_pressure_growth(t) = drawdown_pressure_CN2296.CNI(t)
```

不得增加额外风格层转换。

## 10. 红利通用类别聚合

两项红利 member 必须先分别计算全部四类状态。

### 10.1 正向证据类别

对于 `drawdown_pressure`、`absolute_stabilization` 和 `relative_stabilization`，红利风格状态为 `MET` 当且仅当：

```text
H00015.CSI member state = MET
and
H00922.CSI member state = MET
```

两项均可用但未同时为 `MET` 时，dividend style state 为 `NOT_MET`；任一 member 为 `UNAVAILABLE` 时，dividend style state 为 `UNAVAILABLE`。

### 10.2 风险否决类别

对于 `adverse_continuation`，任一 member 为 `MET` 时红利风格状态为 `MET`：

```text
H00015.CSI = MET or H00922.CSI = MET
```

两项均为 `NOT_MET` 时，dividend adverse_continuation 为 `NOT_MET`；任一 member 为 `UNAVAILABLE` 时为 `UNAVAILABLE`。这是保守聚合，不形成两份红利风险预算。

## 11. Dividend Member Agreement 计算

若任一红利 member 的任一通用类别为 `UNAVAILABLE`：

```text
dividend_member_agreement = UNAVAILABLE
```

若两项 member 在以下四类状态上逐项完全一致：

```text
drawdown_pressure
absolute_stabilization
relative_stabilization
adverse_continuation
```

则 `dividend_member_agreement = AGREEMENT`；否则为 `CONFLICT`。

不得只比较其中一个类别、指定主指数、忽略不一致类别、按历史表现选择 member、将 `CONFLICT` 改写为 `NOT_MET`，或将 `UNAVAILABLE` 改写为 `CONFLICT`。

## 12. 冻结参数配置

V1 只允许以下 3 套完整配置：

| profile | pressure_threshold | absolute_horizon | relative_horizon | adverse_lookback |
| --- | ---: | ---: | ---: | ---: |
| `PROFILE_A` | 0.10 | 10 | 20 | 10 |
| `PROFILE_B` | 0.15 | 20 | 40 | 20 |
| `PROFILE_C` | 0.20 | 40 | 60 | 40 |

horizon 和 lookback 的单位均为 SSE 开放交易日数量。不得给 profile 添加“激进”“稳健”“最佳”等结果导向标签。

## 13. 参数研究边界

三套 profile 必须作为完整配置使用，禁止 Cartesian product。不得把一个 profile 的 `pressure_threshold`、另一个 profile 的 `absolute_horizon` 和第三个 profile 的 `relative_horizon` 重组为新配置。

固定禁止：

- 新增第四套配置或删除表现不佳的配置；
- 对阈值做更细网格搜索；
- 为不同风格、member 或红利使用不同配置；
- 在训练期按事件、年份或市场状态切换配置；
- 使用自动优化器、贝叶斯优化、随机搜索或遗传算法；
- 用全样本结果选择配置；
- 用未来收益、Sharpe、Calmar 或最大回撤扩展参数范围。

所有 5 条 member 序列和 4 个风格单元必须使用同一套完整 profile。本文不决定最终使用哪套 profile。

## 14. 类别独立性

四类通用证据的计算依据保持不同：

- `drawdown_pressure`：当前水平相对运行峰值的压力；
- `absolute_stabilization`：自身固定期限全收益是否非负；
- `relative_stabilization`：自身固定期限全收益是否不弱于 peer 中位数；
- `adverse_continuation`：是否严格创近期新低。

不得复用同一数值条件输出多个类别状态，尤其禁止用 `drawdown <= threshold` 同时决定 pressure 和 stabilization。未来实现偏离上述定义时，候选必须停止，不得构建事件。

## 15. 无前视与精度

所有计算必须只使用观察日期 `t` 及以前的数据，只在 `t` 收盘后可用，最早供下一个 SSE 开放日使用。不得使用 2026-07-15 之后的数据或完整样本统计量回填历史。

状态判定必须使用 JSON 中存储的完整浮点值，比较前不得四舍五入。输出展示可以格式化，但不得以展示精度判定状态。

## 16. 预热期

每套 profile 独立判断可用性。不足相应类别所需历史时返回 `UNAVAILABLE`。

不得使用 2013-01-04 以前的数据补预热，不得缩短窗口、用较短 profile 结果代替、前向或后向填充状态，也不得将 `UNAVAILABLE` 解释为 `NOT_MET`。本文不计算各 profile 的首个完整可用日期。

## 17. 与进入退出合同的关系

本文只负责定义未来可实现的抽象类别状态。状态生成后必须原样交给 [STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md](STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md)。

计算层不得改写进入、退出、同日优先级或并发处理，不得直接生成 ENTRY、HOLD、EXIT、仓位或交易指令。

## 18. 禁止结果与后续顺序

本文不包含实际状态数量、触发日期、风格或参数表现比较、未来收益、事件统计、回测指标、最佳 profile 判断或投资结论。

本文不处理共同面板实现、类别状态实现、事件、walk-forward、仓位、交易成本、回测、`CURRENT_TAA`、ETF、Shadow、execution 或 Web。

本文通过后，下一步最多只能构建确定性共同观察面板并实现三套 profile 的类别状态计算。仍不得构建事件、运行 walk-forward、选择最佳 profile、设计仓位、运行回测或集成 `CURRENT_TAA`。

## 19. 当前状态

```text
Category calculation preregistration status: DEFINED_FOR_REVIEW
Category formula set status: FROZEN_V1
Parameter profile set status: FROZEN_V1
Allowed parameter profile count: 3
Parameter selection status: NOT_RUN
Category calculation implementation status: NOT_IMPLEMENTED
Common panel status: DEFINED_NOT_BUILT
Entry/exit/conflict preregistration status: DEFINED_FOR_REVIEW
Event status: NOT_BUILT
Walk-forward status: NOT_RUN
Allocation status: NOT_DEFINED
Backtest status: NOT_RUN
Integration status: DO_NOT_INTEGRATE
```
