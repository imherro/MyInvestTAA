# Strategy-Style Entry, Exit and Conflict Preregistration V1

## 1. 目的与范围

本文基于已冻结的五类证据，预注册 `Strategy-Style Drawdown Rebalancing` V1 候选的逻辑进入、退出和冲突处理规则。

本文只定义抽象证据状态、四风格的候选逻辑、同日优先级、多风格并发处理、红利双 member 冲突处理，以及数据异常时的阻断语义。

本文不定义或实现证据计算公式、窗口长度、阈值、分位数、均线或波动率周期、排名公式、事件日期、事件 ID、事件持续期、walk-forward、仓位、风格袖套规模、资金分配比例、交易或回测。

## 2. 正式上游合同

本文引用：

- [STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md](STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md)
- [STRATEGY_STYLE_OBSERVATION_DATA_CONTRACT_V1.md](STRATEGY_STYLE_OBSERVATION_DATA_CONTRACT_V1.md)
- [STRATEGY_STYLE_SIGNAL_CATEGORY_PREREGISTRATION_V1.md](STRATEGY_STYLE_SIGNAL_CATEGORY_PREREGISTRATION_V1.md)

本文只落实冻结研究顺序中的第 4 步。五类证据集合已经冻结；本文不改变类别集合，不构建共同面板，不计算证据状态，不构建事件，也不查看历史结果或未来收益。

## 3. 允许的抽象证据状态

### 3.1 通用类别

以下类别未来计算后只能返回 `MET`、`NOT_MET` 或 `UNAVAILABLE`：

```text
drawdown_pressure
absolute_stabilization
relative_stabilization
adverse_continuation
```

本文不定义这些状态的计算方法。

### 3.2 红利 agreement

`dividend_member_agreement` 未来只能返回：

```text
AGREEMENT
CONFLICT
UNAVAILABLE
```

- `AGREEMENT`：两项 member 提供可共同使用的证据；
- `CONFLICT`：两项 member 提供矛盾证据；
- `UNAVAILABLE`：无法形成有效判断。

本文不定义三种状态的数值公式。

## 4. 逻辑状态与逐日结果

每个风格的先前逻辑状态只能是 `INACTIVE` 或 `ACTIVE`。本文不定义 `ACTIVE` 对应任何实际仓位。

每个风格、每个观察日期只能产生以下一个逐日逻辑结果：

```text
BLOCKED
NO_CHANGE
ENTRY_CANDIDATE
HOLD_CANDIDATE
EXIT_CANDIDATE
```

这些结果只是候选规则输出，不是仓位或交易指令。不得输出 `BUY`、`SELL`、`OVERWEIGHT`、`UNDERWEIGHT` 或 `TARGET_WEIGHT`。

## 5. 全局可评估条件

出现以下任一情况时，相关日期和风格必须输出 `BLOCKED`：

- 上游资格报告不再是 `QUALIFIED`；
- 共同面板不完整；
- member 身份或风格映射不一致；
- 该风格规则所需的任一通用证据为 `UNAVAILABLE`；
- 红利 agreement 为 `UNAVAILABLE`；
- 使用 2026-07-15 之后的数据；
- 使用未经资格审计的数据；
- 使用旧 P1 事件、阈值或结果；
- 同日观察存在缺失、重复或未来数据。

`BLOCKED` 不产生进入或退出，不改变先前逻辑状态，不得解释为继续持有或退出，并且必须阻止后续事件构建处理该日期。

## 6. 进入候选规则

### 6.1 Growth

`growth` 只有同时满足以下抽象状态时才能形成 `ENTRY_CANDIDATE`：

```text
drawdown_pressure = MET
absolute_stabilization = MET
relative_stabilization = MET
adverse_continuation = NOT_MET
```

成长必须同时具备绝对和相对稳定证据，`drawdown_pressure = MET` 不得单独形成进入候选。

### 6.2 Value

`value` 的进入条件为：

```text
drawdown_pressure = MET
adverse_continuation = NOT_MET
and one or both of:
  absolute_stabilization = MET
  relative_stabilization = MET
```

至少需要一项稳定证据。

### 6.3 Cash Flow

`cash_flow` 的进入条件与 value 相同：

```text
drawdown_pressure = MET
adverse_continuation = NOT_MET
and one or both of:
  absolute_stabilization = MET
  relative_stabilization = MET
```

### 6.4 Dividend

`dividend` 的进入条件为：

```text
drawdown_pressure = MET
adverse_continuation = NOT_MET
dividend_member_agreement = AGREEMENT
and one or both of:
  absolute_stabilization = MET
  relative_stabilization = MET
```

`dividend_member_agreement = CONFLICT` 时不得进入。红利只产生一个 `ENTRY_CANDIDATE`，不得为两项 member 分别产生候选。

## 7. 进入状态约束

只有先前状态为 `INACTIVE` 时，完整进入条件才能输出 `ENTRY_CANDIDATE`。若先前状态已经是 `ACTIVE`，即使进入条件再次满足，也只能输出 `HOLD_CANDIDATE`。

不得重复进入、叠加进入、产生第二层或多档进入，也不得因条件持续满足而累计增加风险。

## 8. 退出候选规则

先前状态为 `ACTIVE` 时，以下任一条件成立即输出 `EXIT_CANDIDATE`。

### 8.1 持续恶化重新出现

```text
adverse_continuation = MET
```

### 8.2 回撤压力资格消失

```text
drawdown_pressure = NOT_MET
```

这表示原始回撤资格已经正常化，但不要求恢复历史峰值。

### 8.3 稳定证据完全消失

```text
absolute_stabilization = NOT_MET
relative_stabilization = NOT_MET
```

若仍有一项稳定证据存在，不因另一项单独失效而自动退出。

### 8.4 红利证据冲突

仅对 dividend：

```text
dividend_member_agreement = CONFLICT
```

### 8.5 禁止的退出依据

不得仅因未恢复前高、达到固定持有天数、获得固定收益、发生固定亏损、单日下跌、其他风格表现更好，或回测显示某种退出更优而退出。这些条件没有被预注册，也没有合格参数。

## 9. 非活动风格与重新进入

先前状态为 `INACTIVE` 时，即使退出条件成立也只能输出 `NO_CHANGE`，不得为从未进入的风格生成退出候选。

风格形成 `EXIT_CANDIDATE` 并在后续事件层完成逻辑退出后，重新进入必须再次完整满足该风格的全部进入条件。不得自动重新进入、永久禁止重新进入、设置固定冷却期、跳过回撤资格或沿用上次稳定确认。本文不定义冷却期参数。

## 10. 同日规则优先级

单个风格同一观察日期的固定优先级为：

```text
1. BLOCKED
2. EXIT_CANDIDATE
3. ENTRY_CANDIDATE
4. HOLD_CANDIDATE
5. NO_CHANGE
```

因此：

- 数据或证据不可用时不得进入或退出；
- `ACTIVE` 风格同时满足进入和退出逻辑时，退出优先；
- `INACTIVE` 风格同时出现进入逻辑与否决条件时不得进入；
- `adverse_continuation = MET` 不能被稳定证据覆盖；
- 红利 `CONFLICT` 不能被其他红利证据覆盖。

在未阻断且未退出时，`ACTIVE` 风格输出 `HOLD_CANDIDATE`；未形成进入条件的 `INACTIVE` 风格输出 `NO_CHANGE`。

## 11. 多风格同时形成进入候选

多个风格可在同一日期同时形成 `ENTRY_CANDIDATE`。冲突处理固定为：

- 保留所有完整满足进入条件的风格；
- 不进行横截面排名或选择单一赢家；
- 不依据历史收益、回撤更深或反弹更强来选择风格；
- 不删除既有 `ACTIVE` 风格为新候选腾出空间；
- 不在本阶段计算资金分配；
- 不提高风格袖套或总权益预算。

逐日逻辑输出保留一个确定性的 `concurrent_entry_candidate_set`，按以下固定顺序排列，只包含当日实际形成 `ENTRY_CANDIDATE` 的风格：

```text
growth
value
dividend
cash_flow
```

该集合不是配置结果，也不决定权重。

## 12. 多风格退出与混合状态

同一日期允许多个风格同时形成 `EXIT_CANDIDATE`，允许部分风格退出而其他风格保持，也允许部分风格退出而其他风格形成进入候选。

每个风格先独立应用自身规则；一个风格退出不得自动触发另一个风格进入；退出释放的预算不得自动分配给新候选；进入与退出候选不得净额处理。本阶段只保留各风格独立逻辑结果，固定袖套预算的分配只能在后续配置阶段研究。

## 13. 红利冲突处理

- `AGREEMENT`：允许红利继续接受其他进入条件判断；
- `CONFLICT`：对 `INACTIVE` 红利阻止进入，对 `ACTIVE` 红利形成 `EXIT_CANDIDATE`；
- `UNAVAILABLE`：形成 `BLOCKED`，不得解释为 `CONFLICT` 或 `NOT_MET`。

不得指定主红利指数、使用表现更好的一项、忽略发生冲突的 member、生成两个红利状态或生成两份红利风险预算。

## 14. 类别独立性延续

不得使用同一个数值条件同时计算 `drawdown_pressure = MET` 和 `absolute_stabilization = MET` 或 `relative_stabilization = MET`。本文只组合未来独立产生的类别状态，不允许通过规则组合绕过类别独立性要求。

若后续类别计算无法证明压力与稳定证据具有不同定义，候选必须停止，不得进入事件构建。

## 15. 与事件层隔离

本文不定义 event start date、event end date、event ID、event duration、recovery date、trigger date、execution date、outcome window、forward return、同一风格事件如何切分或连续候选如何合并。

`ENTRY_CANDIDATE`、`HOLD_CANDIDATE` 和 `EXIT_CANDIDATE` 只是逐日逻辑结果。事件事实只能在后续独立任务中定义和构建。

## 16. 参数保持未定义

本文中的 `MET`、`NOT_MET`、`AGREEMENT` 和 `CONFLICT` 只是抽象状态，不表示已经存在计算方法。本任务通过后仍保持：

```text
Parameter status: NOT_DEFINED
Category calculation status: NOT_IMPLEMENTED
```

下一步不得直接构建事件，应先单独预注册五类证据的计算定义与参数研究边界；本文不提前定义公式或参数。

## 17. 后续顺序

本文通过后只能进入“预注册五类证据的计算定义与参数研究边界”。不得直接构建共同面板、计算类别状态、构建事件、运行 walk-forward、设计仓位、运行回测或集成 `CURRENT_TAA`。

## 18. 当前状态

```text
Entry/exit/conflict preregistration status: DEFINED_FOR_REVIEW
Signal category set status: FROZEN_V1
Observation contract status: DEFINED_FOR_REVIEW
Parameter status: NOT_DEFINED
Category calculation status: NOT_IMPLEMENTED
Common panel status: DEFINED_NOT_BUILT
Event status: NOT_BUILT
Walk-forward status: NOT_RUN
Allocation status: NOT_DEFINED
Backtest status: NOT_RUN
Integration status: DO_NOT_INTEGRATE
```
