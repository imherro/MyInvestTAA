# Strategy-Style Candidate Signal Category Preregistration V1

## 1. 目的与范围

本文为 `Strategy-Style Drawdown Rebalancing` 预注册允许进入下一阶段研究的候选信号类别。它只说明每类证据回答的经济问题、允许使用的观察字段、适用的风格，以及禁止的数据和研究结果。

本文不定义窗口长度、阈值、分位数、移动平均或波动率周期、参考区间、z-score 公式、排名方法、布尔组合、进入规则、退出规则、冲突处理、事件、walk-forward、仓位或回测。

## 2. 正式上游合同

本文引用：

- [STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md](STRATEGY_STYLE_DRAWDOWN_REBALANCING_MECHANISM_V1.md)
- [STRATEGY_STYLE_OBSERVATION_DATA_CONTRACT_V1.md](STRATEGY_STYLE_OBSERVATION_DATA_CONTRACT_V1.md)

本文只落实冻结研究顺序中的第 3 步，不修改机制合同或观察合同，不生成共同面板，不计算任何历史信号，不查看未来收益结果，也不产生进入、退出或配置结论。

## 3. 固定风格决策单元

信号类别只服务 4 个风格单元：

| style unit | member asset | 正式名称 |
| --- | --- | --- |
| growth | `CN2296.CNI` | 创成长R |
| value | `CN2371.CNI` | 国证价值R |
| dividend | `H00015.CSI` | 红利收益 |
| dividend | `H00922.CSI` | 中红收益 |
| cash_flow | `480092.CNI` | 国证自由现金流指数R |

不得引入宽基、主题、资源、行业、ETF 或单只股票。

## 4. 允许的候选信号类别

V1 只允许以下 5 类证据。

### 4.1 Drawdown Pressure Eligibility

正式类别标识：`drawdown_pressure`

回答的问题：某个风格是否承受了足够值得进一步观察的价格压力？

允许使用：

```text
drawdown
running_peak_level
normalized_level
```

该类别只描述压力程度，不构成买入或增配指令，不得单独形成信号。不得使用旧失败候选的 p75、p90 或 p95；本文不定义何种压力程度算“足够”。

### 4.2 Absolute Price-Path Stabilization

正式类别标识：`absolute_stabilization`

回答的问题：在自身价格路径上，该风格的恶化是否表现出停止或减缓的迹象？

允许使用：

```text
daily_total_return
normalized_level
cumulative_total_return
running_peak_level
drawdown
```

该类别只能使用风格自身的 member 序列，不得引用未来收益。本文不定义趋势、反转、均线或窗口公式，也不得把单日上涨直接定义为稳定。

### 4.3 Relative Price-Path Stabilization

正式类别标识：`relative_stabilization`

回答的问题：相对于其他策略风格，该风格是否不再继续恶化？

允许使用四个风格在共同日期上的观察字段。必须使用从 2013-01-04 开始的共同面板，只能比较同一观察日期以前已经可知的数据，不得使用价值或红利更长的原生历史。

本文不定义相对比率、参考组合、排名或窗口，也不得将该类别演变为选择“当前最强风格”的轮动策略。

### 4.4 Adverse Continuation Guardrail

正式类别标识：`adverse_continuation`

回答的问题：该风格是否仍处于明显的持续恶化状态，使回撤再平衡不应被考虑？

允许使用：

```text
daily_total_return
normalized_level
running_peak_level
drawdown
```

该类别是风险警示或后续规则中的否决候选，不是独立增配信号。本文不定义何时属于持续恶化、否决持续多久、是否覆盖其他类别，也不定义任何波动率或趋势参数。

### 4.5 Dividend Member Agreement

正式类别标识：`dividend_member_agreement`

只适用于 `dividend`，回答的问题是：红利收益与中红收益是否提供方向一致、互相矛盾或无法判断的证据？

只允许使用 `H00015.CSI` 与 `H00922.CSI` 各自的 member observations。两项指数必须对称处理，不得指定主指数和备用指数，不得平均或合成为一条价格序列，不得依据历史表现只保留一项，也不得产生两份红利信号或风险预算。

本文不定义“一致”“矛盾”或“无法判断”的计算公式，也不决定两项是否必须同时通过。

## 5. 统一类别架构

四个风格均允许使用：

```text
drawdown_pressure
absolute_stabilization
relative_stabilization
adverse_continuation
```

红利额外使用：

```text
dividend_member_agreement
```

不得为单个风格事后新增专属类别。后续规则任务可以在查看回测结果前，为不同风格预注册不同的严格程度或类别组合，但只能从本文允许的类别中选择，不得新增第 6 类，不得删除红利 member agreement，且成长不得仅使用 `drawdown_pressure`。

## 6. 类别独立性

`drawdown_pressure` 回答“是否承受值得进一步观察的压力”，而 `absolute_stabilization`、`relative_stabilization` 和 `adverse_continuation` 回答价格路径是否停止恶化或仍在恶化。它们是不同的经济问题。

即使这些类别都来自价格数据，也不得把“达到某个回撤深度”同时包装成“压力条件已满足”和“稳定条件已满足”。后续实现必须避免将同一个数值条件重复计为多个独立证据。本文不定义类别独立性的检验或实现方法。

## 7. V1 禁止使用的信号类别

V1 明确禁止：

```text
valuation
earnings
dividend_yield
cash_flow_fundamentals
quality_fundamentals
macro_regime
interest_rate
credit
fund_flow
ETF_flow
sentiment
industry_breadth
stock_breadth
volatility_targeting
option_implied_signal
```

P2-Task-01 独立数据集没有这些正式数据，不得从 `CURRENT_TAA` 或网络临时补充，也不得以“只是确认条件”为由绕过数据资格流程。未来如需使用，必须先建立新的独立数据接入和资格审计任务，不得直接修改本候选。

## 8. 禁止使用的研究结果

类别选择、删除或风格差异不得使用：

- P1 回撤加仓候选的 p75、p90、p95；
- 旧候选 70/80/90/100 的结果；
- 旧回撤 event、outcome 或 walk-forward 报告；
- 未来 1 年或 2 年收益；
- 事后最大回撤、Calmar 或 Sharpe；
- 表现最好的资产或风格；
- 2026-07-15 之后的数据。

## 9. 红利边界

每天仍只有 1 个 `dividend style bundle` 和 2 条 `dividend member observations`。`dividend_member_agreement` 只是证据类别，不是红利合成指数、第五个风格、第二份红利信号或第二份红利风险预算。

后续规则必须同时说明如何处理两项证据一致、不一致，以及其中一项无法判断，但本文不定义这些处理规则。

## 10. 与进入、退出和冲突规则隔离

本文只批准可以研究的证据类别，不决定：

```text
drawdown_pressure AND absolute_stabilization
drawdown_pressure AND relative_stabilization
需要几类确认
哪类具有否决权
成长是否需要更多确认
红利不一致时如何处理
退出使用哪个类别
多个风格同时满足时如何分配
```

以上全部属于下一阶段“预注册进入、退出和冲突处理规则”，不得在本文提前决定。

继续有效的机制约束是：`drawdown is an eligibility input, not a direct allocation command`。后续规则不得让 `drawdown_pressure` 单独触发配置动作。

## 11. 类别冻结规则

P2-Task-04 通过后，允许的 V1 信号类别集合冻结为：

```text
drawdown_pressure
absolute_stabilization
relative_stabilization
adverse_continuation
dividend_member_agreement
```

进入后续规则设计后，不得根据结果增加或删除类别，不得将同一公式复制成两个类别，不得将不支持结果的类别改名后重测，不得为单个风格增加新专属类别，也不得把禁止数据源包装成现有类别。

如需改变类别集合，必须停止当前候选、建立新的候选版本、在查看新结果前重新预注册，并且不得覆盖 V1 文档。

## 12. 非目标与后续顺序

本文不处理共同面板构建、数值计算、信号状态、阈值、窗口、参数网格、进入、退出、冲突、事件、walk-forward、仓位、交易成本、回测、`CURRENT_TAA` 接入、ETF、Shadow、execution 或 Web。

本任务通过后，下一步只能是“预注册进入、退出和冲突处理规则”，不得直接构建共同面板、计算信号、构建事件、运行 walk-forward、设计仓位、运行回测或集成 `CURRENT_TAA`。

## 13. 当前状态

```text
Signal category preregistration status: DEFINED_FOR_REVIEW
Allowed signal category count: 5
Observation contract status: DEFINED_FOR_REVIEW
Parameter status: NOT_DEFINED
Entry and exit status: NOT_DEFINED
Conflict handling status: NOT_DEFINED
Event status: NOT_BUILT
Walk-forward status: NOT_RUN
Allocation status: NOT_DEFINED
Integration status: DO_NOT_INTEGRATE
```
