# Strategy-Style Logic Event Construction Preregistration V1

## 1. 目的与范围

本文预注册如何把 P2-Task-08 的逐日逻辑状态转换为确定性的事件事实。本文只冻结事件的构成、起止、开放事件、阻断日期、重新进入、编号、字段和完整性边界。

本文不实现事件构建，不生成事件数据，不计算未来结果，不定义 outcome 窗口，不运行 walk-forward，不比较或选择 profile，不设计仓位或资金分配，不计算交易成本，不运行回测，也不接入 `CURRENT_TAA`。

## 2. 正式上游输入

本文引用以下正式上游：

- [STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md](STRATEGY_STYLE_ENTRY_EXIT_CONFLICT_PREREGISTRATION_V1.md)
- [STRATEGY_STYLE_DAILY_LOGIC_ARTIFACT_V1.md](STRATEGY_STYLE_DAILY_LOGIC_ARTIFACT_V1.md)
- `data/strategy_style_daily_logic_v1/manifest.json`
- `data/strategy_style_daily_logic_v1/daily_logic.json`

正式输入身份固定为：

```text
source artifact set: STRATEGY_STYLE_DAILY_LOGIC_ARTIFACT_V1
source dataset: STRATEGY_STYLE_DAILY_LOGIC_V1
source as-of: 2026-07-15
date count: 3284
profile order: PROFILE_A PROFILE_B PROFILE_C
style order: growth value dividend cash_flow
```

本合同不得重新计算类别状态或状态机结果。

## 3. 事件隔离单位

事件只能在 `profile_id × style_unit` 内独立构建，共有 `3 profiles × 4 styles = 12 independent event streams`。

不得跨 profile 或跨 style 合并事件，不得把同日多个进入候选合成组合事件，不得把红利拆成两个 member 事件，也不得用其他 style 的退出终止当前 style 事件。

`concurrent_entry_candidate_set` 只用于核对同日并发事实，不参与事件合并。

## 4. 事件开始

一个事件当且仅当某个独立事件流在日期索引 `t` 满足：

```text
state_before[t] = INACTIVE
daily_result[t] = ENTRY_CANDIDATE
state_after[t] = ACTIVE
```

固定定义：

```text
event_start_index = t 的 0-based 共同日期索引
event_start_observation_date = common_panel.dates[t]
```

不得使用前一个 `BLOCKED` 日期、回撤开始日期、首次 pressure 满足日期、类别状态首次可用日期、下一交易日或假设的执行日期作为事件起点。`event_start_observation_date` 只是逻辑进入候选形成的观察日期，不是买入日期。

## 5. 事件结束

一个已开始事件在进入之后首次满足以下条件的日期索引 `t` 结束：

```text
state_before[t] = ACTIVE
daily_result[t] = EXIT_CANDIDATE
state_after[t] = INACTIVE
```

固定定义：

```text
event_end_index = t 的 0-based 共同日期索引
event_end_observation_date = common_panel.dates[t]
event_status = CLOSED
```

必须使用进入后的首个 `EXIT_CANDIDATE`。`BLOCKED`、`HOLD_CANDIDATE`、`NO_CHANGE`、恢复前高、固定天数、固定损益、其他 style 的进入候选或 profile 样本表现均不得结束事件。

## 6. 开放事件

若事件开始后，截至 2026-07-15 仍未出现 `EXIT_CANDIDATE`，固定记录：

```text
event_status = OPEN
event_end_index = null
event_end_observation_date = null
last_observation_index = 3283
last_observation_date = 2026-07-15
```

不得在样本末日强制退出，不得把 `OPEN` 改写为 `CLOSED`，不得使用未来日期补结束，也不得删除开放事件。

## 7. 事件区间与观察日数量

### 7.1 CLOSED 事件

观察区间为 `[event_start_index, event_end_index]`，包含开始日和结束日：

```text
observation_session_count = event_end_index - event_start_index + 1
```

状态机不允许同日同时进入和退出，因此 `CLOSED` 事件的 `observation_session_count >= 2`。

### 7.2 OPEN 事件

观察区间为 `[event_start_index, 3283]`：

```text
observation_session_count = 3283 - event_start_index + 1
```

该数量只是样本内观察日数量，不是持仓天数。

## 8. BLOCKED 日期

若事件开始后出现：

```text
daily_result = BLOCKED
state_before = ACTIVE
state_after = ACTIVE
```

该日期保留在事件区间内，不终止或拆分事件，不形成新事件，不视为 `HOLD_CANDIDATE`，也不从观察日数量中删除。

每个事件允许记录 `blocked_session_count`，定义为事件区间内 `daily_result=BLOCKED` 的日期数量。不得对阻断日期进行收益填充、状态推断或退出假设。

## 9. HOLD 日期

事件区间内 `daily_result=HOLD_CANDIDATE` 的日期允许计入 `hold_session_count`。它不产生新事件，不修改事件起点，不延迟已经出现的退出，也不代表实际持仓或交易行为。

## 10. 重新进入

一个 `CLOSED` 事件结束后，该事件流回到 `INACTIVE`。以后出现新的完整 `ENTRY_CANDIDATE` 时，必须创建新事件。

不得与上一个事件合并，不得因间隔较近而合并，不得设置未经预注册的冷却期，不得继承上一个开始日期，也不得把多个事件视为一个长期回撤周期。

## 11. 事件重叠不变量

同一 `profile_id × style_unit` 的事件不得重叠：

```text
previous event end_index < next event start_index
```

`OPEN` 事件必须是该事件流的最后一个事件，其后不得存在新事件。不同 style 或不同 profile 的事件可以在日期上重叠，但仍保持独立。

## 12. 事件 ID

每个事件流从 1 开始独立编号，按 `event_start_index` 升序。固定格式为：

```text
{profile_id}__{style_unit}__{sequence:04d}
```

示例：

```text
PROFILE_A__growth__0001
PROFILE_A__growth__0002
PROFILE_B__dividend__0001
```

ID 在相同输入下必须确定，不使用随机数、时间戳、收益、回撤或表现信息，也不因其他 profile 或 style 新增事件而改变本事件流既有 ID。

## 13. 允许的事件事实字段

后续事件实现只允许每条事件包含：

```text
event_id
profile_id
style_unit
member_asset_ids
sequence_number
event_status
event_start_index
event_start_observation_date
event_end_index
event_end_observation_date
last_observation_index
last_observation_date
observation_session_count
blocked_session_count
hold_session_count
source_entry_result
source_exit_result
```

固定语义：

```text
source_entry_result = ENTRY_CANDIDATE
CLOSED: source_exit_result = EXIT_CANDIDATE
OPEN: source_exit_result = null
```

## 14. 明确禁止的事件字段

V1 事件事实不得包含：

```text
trigger_price entry_price exit_price execution_date trade_date
position weight allocation capital transaction_cost
forward_return event_return annualized_return excess_return
maximum_drawdown Sharpe Calmar outcome success failure
best_profile selected_profile profile_rank style_rank
```

不得通过别名加入上述内容。

## 15. 与交易隔离

`event_start_observation_date` 不是 `trade_entry_date`、`execution_date` 或 `position_start_date`；`event_end_observation_date` 不是 `trade_exit_date`、`execution_date` 或 `position_end_date`。

事件只描述冻结逻辑状态机的状态区间。执行延迟、交易价格、成本或资金变化必须留到后续独立任务。

## 16. 与未来结果隔离

事件构建不得读取事件结束后的价格、固定未来收益窗口、事件后 1 个月、3 个月、6 个月或 1 年收益、事后最大回撤、profile 绩效或组合绩效。

事件边界只能由 `ENTRY_CANDIDATE`、`EXIT_CANDIDATE` 及对应状态转换决定。

## 17. 事件完整性不变量

后续实现必须满足以下十二项：

1. 每个 `ENTRY_CANDIDATE` 恰好对应一个事件开始。
2. 每个 `CLOSED` 事件恰好对应一个进入后的首次 `EXIT_CANDIDATE`。
3. 每个 `EXIT_CANDIDATE` 恰好关闭一个 `ACTIVE` 事件。
4. 不存在无 `ENTRY_CANDIDATE` 的事件。
5. 不存在无 `ACTIVE` 状态的 `CLOSED` 事件。
6. 同一事件流内不存在重叠事件。
7. 每个事件流最多一个 `OPEN` 事件。
8. `OPEN` 事件只能位于事件流末尾。
9. `BLOCKED` 不增加或减少事件数量。
10. `HOLD_CANDIDATE` 不增加或减少事件数量。
11. 事件顺序只由共同日期索引决定。
12. 同日并发进入在不同 style 中形成独立事件。

## 18. 后续实现产物预留

后续独立实现任务可以生成 `data/strategy_style_logic_events_v1/`，预期只包含 `manifest.json` 和 `events.json`。本文不得创建该目录或任何事件文件。

事件实现不得修改 `data/strategy_style_daily_logic_v1/`、`data/strategy_style_category_calculations_v1/` 或 `data/strategy_style_research/`。

## 19. 当前状态

```text
Event construction preregistration status: DEFINED_FOR_REVIEW
Daily logic state machine status: IMPLEMENTED
Event construction implementation status: NOT_IMPLEMENTED
Event dataset status: NOT_BUILT
Forward outcome status: NOT_COMPUTED
Walk-forward status: NOT_RUN
Parameter profile selection status: NOT_RUN
Allocation status: NOT_DEFINED
Backtest status: NOT_RUN
Integration status: DO_NOT_INTEGRATE
```

不得标记为 `APPROVED`、`EVENT_READY`、`OUTCOME_READY`、`BEST_PROFILE`、`BACKTEST_READY` 或 `PRODUCTION_READY`。

