# Strategy-Style Forward Outcome and Walk-Forward Preregistration V1

## 1. 目的与范围

本文在查看任何未来结果之前，冻结策略风格事件的未来结果定义、时间可用性、年度样本划分、汇总指标、profile 支持门槛和确定性选择规则。

本文只定义结果与严格时间外评价合同，不计算任何实际收益，不读取或报告事件结果，不创建结果数据，不运行 walk-forward，不判断 profile 优劣，不选择 profile，不设计仓位或分配资金，不计算交易成本，不运行组合回测，也不接入 `CURRENT_TAA`。

## 2. 正式上游身份

本文引用以下正式上游：

- [STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1.md](STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1.md)
- [STRATEGY_STYLE_LOGIC_EVENT_ARTIFACT_V1.md](STRATEGY_STYLE_LOGIC_EVENT_ARTIFACT_V1.md)
- `data/strategy_style_logic_events_v1/manifest.json`
- `data/strategy_style_logic_events_v1/events.json`
- `data/strategy_style_category_calculations_v1/common_panel.json`

固定身份为：

```text
event artifact: STRATEGY_STYLE_LOGIC_EVENTS_ARTIFACT_V1
event dataset: STRATEGY_STYLE_LOGIC_EVENTS_V1
source as-of: 2026-07-15
common date count: 3284
event stream count: 12
profile order: PROFILE_A PROFILE_B PROFILE_C
style order: growth value dividend cash_flow
```

不得从 category states、daily logic 或原始价格重新构建事件。

## 3. 后续实现的输入边界

后续结果实现只允许读取：

```text
data/strategy_style_logic_events_v1/manifest.json
data/strategy_style_logic_events_v1/events.json
data/strategy_style_category_calculations_v1/common_panel.json
docs/STRATEGY_STYLE_FORWARD_OUTCOME_WALK_FORWARD_PREREGISTRATION_V1.md
docs/STRATEGY_STYLE_EVENT_CONSTRUCTION_PREREGISTRATION_V1.md
```

实现可以读取事件 manifest 登记的合同以校验 SHA 链，但不得重新计算事件。`common_panel.json` 中五项资产的原始 `close` 数组是唯一正式收益来源。

禁止读取：

```text
data/strategy_style_category_calculations_v1/category_states.json
data/strategy_style_daily_logic_v1/daily_logic.json
data/strategy_style_research/prices/
data/research_prices/
reports/current/
旧 P1 结果
CURRENT_TAA 结果
ETF
Shadow
execution
Web
```

## 4. 结果计算时间语义

事件开始观察日的状态只在该日收盘后可知，因此固定：

```text
evaluation_start_index = event_start_index + 1
evaluation_start_date = common_panel.dates[evaluation_start_index]
```

如果 `evaluation_start_index > 3283`，该事件的所有未来结果均为 `UNAVAILABLE_AS_OF`。不得使用事件开始日收盘价作为结果起点。

`evaluation_start_date` 只是避免使用形成信号当日收盘价的滞后一日结果参考点，不得称为交易日、实际买入日或执行日。

## 5. Member 期限收益

对 member `m`、结果起点 `a` 和终点 `b`，固定：

```text
member_total_return(m, a, b) = close_m[b] / close_m[a] - 1
```

要求 `0 <= a < b <= 3283`。必须直接使用 common panel 的原始 `close` 值，并以原始浮点精度判断状态和保存结果。

不得使用 normalized level 比率替代，不得使用四舍五入价格、自然日、插值、前向填充、后向填充或共同起点以前的数据。

## 6. 四个 Style Unit 的结果收益

### 6.1 单 member style

固定 member：

```text
growth: CN2296.CNI
value: CN2371.CNI
cash_flow: 480092.CNI
```

对应的 `style_total_return` 直接等于唯一 member 的期限收益。

### 6.2 Dividend family

红利固定包含：

```text
H00015.CSI
H00922.CSI
```

必须分别保存两项 member 期限收益。只有两项均可计算时，结果层才允许定义：

```text
dividend_family_total_return =
  (H00015.CSI member_total_return + H00922.CSI member_total_return) / 2
```

该平均值只用于结果层把红利作为一个 style unit 比较。它不是合成价格指数，不回写 common panel，不参与信号或事件构建，不产生第二份红利风险预算，不允许根据历史表现改变 50/50，不允许选定主红利指数，也不允许只使用表现较好的一项。任一红利 member 不可用时，红利 family 结果必须不可用。

## 7. Peer Benchmark

事件所属 style `s` 的 peer 集合固定为另外三个 style unit。例如，growth 的 peers 是 value、dividend 和 cash_flow。

```text
peer_benchmark_total_return(s, a, b) =
  其他三个 style_total_return 的算术平均值
```

每个 style unit 只占 peer benchmark 的三分之一，红利 family 只计一次。任一 peer style 结果不可用时，peer benchmark 和相对结果均不可用。

不得使用五 member 等权平均，不得双重计算红利，不得按历史表现调整 peer 权重，不得排除表现不佳的 peer，也不得使用 `CURRENT_TAA` 或宽基作为 benchmark。

## 8. 核心相对结果

固定定义：

```text
peer_relative_return = style_total_return - peer_benchmark_total_return
```

该值只衡量事件 style 相对于其他三个策略风格的同期表现。它不是 alpha、交易利润、组合超额收益、实际重仓贡献或扣费收益。正值只表示事件 style 同期优于三个 peer style 的等权结果。

## 9. 固定期限结果

只允许以下三个固定期限：

```text
H20 = 20 个 SSE 开放交易日
H60 = 60 个 SSE 开放交易日
H120 = 120 个 SSE 开放交易日
```

固定：

```text
horizon_end_index(H) = evaluation_start_index + H
```

若 `horizon_end_index(H) <= 3283`，该期限状态为 `AVAILABLE`；否则为 `UNAVAILABLE_AS_OF`。

不得缩短期限、使用最近可用日期代替、对部分期限年化、用较短期限代替较长期限、使用 20/60/120 以外的期限，或根据结果新增期限。H60 是正式主要期限，H20 和 H120 是次要稳健性期限。

## 10. CLOSED Episode 结果

`CLOSED` 事件额外定义完整状态机区间结果：

```text
episode_start_index = event_start_index + 1
episode_end_index = event_end_index + 1
```

仅当以下三项同时成立时，episode 结果为 `AVAILABLE`：

```text
episode_start_index <= 3283
episode_end_index <= 3283
episode_start_index < episode_end_index
```

否则为 `UNAVAILABLE_AS_OF`。`OPEN` 事件的 episode 结果固定为 `NOT_CLOSED`。

不得使用 `event_end_index` 当日收盘价作为 episode 终点，因为退出候选只在该日收盘后形成。episode 同样计算 `style_total_return`、`peer_benchmark_total_return` 和 `peer_relative_return`。它只是状态机逻辑区间的滞后一日观察结果，不是交易回测。

## 11. 结果可用性枚举

只允许：

```text
AVAILABLE
UNAVAILABLE_AS_OF
NOT_CLOSED
```

固定期限只允许 `AVAILABLE` 或 `UNAVAILABLE_AS_OF`；`CLOSED` episode 只允许 `AVAILABLE` 或 `UNAVAILABLE_AS_OF`；`OPEN` episode 固定为 `NOT_CLOSED`。

不可用结果的所有数值字段必须为 `null`。不得输出 NaN 或 Infinity，不得使用零代替不可用，不得删除不可用事件，不得把 OPEN episode 视为亏损或盈利，也不得根据结果是否有利决定保留结果。

## 12. 事件结果事实预留字段

后续实现的事件结果记录可以包含：

```text
event_id
profile_id
style_unit
event_status
event_start_observation_date
evaluation_start_index
evaluation_start_date
walk_forward_partition
walk_forward_fold_id
H20
H60
H120
episode
```

每个期限对象可以包含：

```text
availability_status
evaluation_end_index
evaluation_end_date
member_total_returns
style_total_return
peer_style_total_returns
peer_benchmark_total_return
peer_relative_return
```

不得把这些字段写回正式事件数据集。不得加入权重、仓位、资金、交易成本、实际买卖价格、组合收益或回测净值。

## 13. 时间样本划分

事件只按 `event_start_observation_date` 分区。

### 13.1 Development exclusion

开始日期在 2013-01-04 至 2017-12-31 的事件固定标记：

```text
walk_forward_partition = DEVELOPMENT_EXCLUDED
walk_forward_fold_id = null
```

这些事件可以保留在结果数据集中以便完整审计，但不得进入正式 walk-forward 汇总、profile 支持判断或选择。不得根据 development 结果修改 profile、公式或门槛。

### 13.2 正式年度 OOS folds

固定八个 fold：

```text
WF_2018
WF_2019
WF_2020
WF_2021
WF_2022
WF_2023
WF_2024
WF_2025
```

事件按开始观察日期所属公历年分配。profile 和公式在所有 fold 中保持完全不变。

### 13.3 Prospective partition

开始日期在 2026-01-01 至 2026-07-15 的事件固定标记：

```text
walk_forward_partition = PROSPECTIVE_NOT_SCORED
walk_forward_fold_id = null
```

这些事件可以生成截至 as-of 可用的结果事实，但不得进入正式八 fold 汇总或 profile 选择。不得因 2026 结果较好而将其加入正式样本。

## 14. 严格时间边界

固定期限结果允许终点跨越事件开始年份。例如，WF_2025 事件的 H120 终点可以位于 2026 年，但必须只使用固定期限终点，终点不得晚于 2026-07-15，不使用该结果修改更早 fold，也不进行滚动参数重估。

本研究不存在训练期参数拟合。Walk-forward 在 V1 中的严格含义是：三套已经冻结的 profile，在固定的连续年度样本上按时间顺序进行完全不调参的 out-of-time 评价。

不得在 fold 之间重选参数，不得根据上一 fold 结果切换 profile，不得删除表现差的年度，不得更改结果期限，不得对不同年份使用不同公式，也不得使用全样本结果修改门槛。

## 15. 事件级指标

每个 `AVAILABLE` 期限保留：

```text
style_total_return
peer_benchmark_total_return
peer_relative_return
```

正式方向判断使用原始精度：

```text
peer_relative_return > 0: POSITIVE
peer_relative_return = 0: FLAT
peer_relative_return < 0: NEGATIVE
```

不得把 POSITIVE 称为投资成功或盈利交易。

## 16. 正式汇总层级

### 16.1 Profile x Style x Fold x Horizon

每个单元固定报告：

```text
eligible_event_count
unavailable_event_count
median_style_total_return
median_peer_relative_return
positive_count
flat_count
negative_count
positive_rate
```

`positive_rate = positive_count / (positive_count + flat_count + negative_count)`。无 `AVAILABLE` 事件时，所有汇总值为 `null`，状态为 `NO_ELIGIBLE_EVENTS`。

### 16.2 Profile x Style x Horizon

只使用八个正式 OOS folds，固定报告：

```text
available_fold_count
positive_fold_count
flat_fold_count
negative_fold_count
median_of_fold_median_peer_relative_return
```

每个 fold 的方向由该 fold 的 `median_peer_relative_return` 确定，不得用事件数量作为 fold 权重。

### 16.3 Profile x Fold x Horizon

固定计算该 profile 在该 fold 中四个 style 级中位数的中位数，只纳入当 fold 有 `AVAILABLE` 事件的 style，并报告 `available_style_count`。无可用 style 时状态为 `NO_ELIGIBLE_EVENTS`。不得按 style 事件数量加权。

### 16.4 Profile x Horizon

固定报告：

```text
available_fold_count
positive_fold_count
flat_fold_count
negative_fold_count
median_of_profile_fold_medians
```

不得直接用 1122 个事件整体平均值代替年度 fold 汇总。

## 17. 重叠事件和统计边界

不同 profile 或 style 的结果可能在时间上重叠。V1 不得把重叠事件当作独立样本计算 p 值，不得输出 t 统计量或未经聚类处理的置信区间，不得声称统计显著，也不得根据事件数量制造精确度。

正式判断只使用中位数、正负方向计数、年度 fold 一致性和 style 覆盖情况。不得运行机器学习分类器或自动优化器。

## 18. Profile 支持门槛

H60 是唯一主要决策期限。每套 profile 独立计算以下四项条件。

### 条件 A：Style 广度

四个 style 中至少三个满足：

```text
median_of_fold_median_peer_relative_return(H60) > 0
```

无足够 `AVAILABLE` fold 的 style 视为不满足，不得删除。

### 条件 B：年度一致性

八个正式年度 fold 中至少五个满足：

```text
profile_fold_median_peer_relative_return(H60) > 0
```

`NO_ELIGIBLE_EVENTS` 的 fold 不计为正向。

### 条件 C：主要期限总体方向

```text
median_of_profile_fold_medians(H60) > 0
```

### 条件 D：次要期限确认

H20 或 H120 至少一个满足：

```text
median_of_profile_fold_medians > 0
```

只有同时满足 A、B、C、D 时，该 profile 在后续实现中才可以标记为 `WALK_FORWARD_SUPPORTED`；否则标记为 `NOT_SUPPORTED`。本文只冻结规则，不执行实际判定。

## 19. Profile 选择规则

本文不执行选择，只预注册后续确定性选择规则。

### 19.1 无支持 profile

若没有 profile 为 `WALK_FORWARD_SUPPORTED`：

```text
mechanism decision = REJECTED
selected_profile = null
```

不得进入仓位设计。

### 19.2 单一支持 profile

若只有一个 profile 受支持：

```text
mechanism decision = SUPPORTED
selected_profile = 该 profile
```

### 19.3 多个支持 profile

依次使用以下固定顺序比较：

1. H60 正向年度 fold 数量更多。
2. H60 正向 style 数量更多。
3. H60 的 `median_of_profile_fold_medians` 更高。
4. H120 的 `median_of_profile_fold_medians` 更高。

全部相同时：

```text
mechanism decision = AMBIGUOUS
selected_profile = null
```

不得默认选择 PROFILE_A、PROFILE_B 或 PROFILE_C，不得因参数更激进或保守而主观选择，不得使用事件数量作为优先级，不得使用 development 或 2026 prospective 结果打破平局，也不得使用仓位回测结果倒推 profile。

规则状态固定为：

```text
Profile selection rule status: FROZEN_V1
Profile selection execution status: NOT_RUN
```

## 20. Episode 结果用途

Episode 结果只作为状态机退出规则的补充诊断，不得替代 H60 主要决策期限。固定报告：

```text
CLOSED available episode count
episode median peer-relative return
episode positive count
episode flat count
episode negative count
OPEN count
episode UNAVAILABLE_AS_OF count
```

不得因为 OPEN 事件缺少 episode 结果而删除它或假设退出。

## 21. 结果解释边界

后续结果不得直接称为策略回测收益、实盘收益、组合 alpha、重仓收益、扣费收益、可交易利润、成功率或胜率。

允许使用 `positive peer-relative outcome rate`，不得简写为 `win rate`。

## 22. 后续产物预留

未来独立实现任务最多可以建立：

```text
data/strategy_style_walk_forward_v1/
```

并生成：

```text
manifest.json
event_outcomes.json
walk_forward_summary.json
```

本文不创建这些文件或目录。未来实现不得修改：

```text
data/strategy_style_logic_events_v1/
data/strategy_style_daily_logic_v1/
data/strategy_style_category_calculations_v1/
data/strategy_style_research/
```

## 23. 当前状态

```text
Forward outcome preregistration status: DEFINED_FOR_REVIEW
Outcome formula set status: FROZEN_V1
Walk-forward protocol status: DEFINED_FOR_REVIEW
Walk-forward fold set status: FROZEN_V1
Primary horizon: H60
Secondary horizons: H20 H120
Profile support rule status: FROZEN_V1
Profile selection rule status: FROZEN_V1
Forward outcome implementation status: NOT_IMPLEMENTED
Forward outcome dataset status: NOT_BUILT
Walk-forward status: NOT_RUN
Profile selection execution status: NOT_RUN
Allocation status: NOT_DEFINED
Backtest status: NOT_RUN
Integration status: DO_NOT_INTEGRATE
```

本文不得标记为 `APPROVED`、`OUTCOME_READY`、`WALK_FORWARD_READY`、`WALK_FORWARD_SUPPORTED`、`SELECTED_PROFILE`、`BEST_PROFILE`、`BACKTEST_READY` 或 `PRODUCTION_READY`。

## 24. 冻结边界

本文冻结的是未来实现合同，而不是研究结果。本文没有计算实际事件收益，没有形成 profile、年度或期限结果，没有执行支持或拒绝判定，没有选择 profile，没有定义仓位比例或资金配置，没有引入交易成本，也没有生成回测净值。

任何后续实现都必须在单独任务中按照本文合同执行，并保持 P2-Task-10 及以前的代码、数据、合同和 `CURRENT_TAA` 正式链不变。
