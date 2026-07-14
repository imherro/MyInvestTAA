# Execution V2

## 当前定位

Execution V2 B1 是 `core_candidate`，采用固定的 `zero_cost_core_semantics`。它目前不替换 Execution V1，不进入 Current Decision，不参与正式 release gate，且 `production_actionable=false`。

Execution V2 B2 是 `frozen_archived_research_experiment`。它只保留历史代码和产物，不属于核心完成标准，也没有后续开发计划。详细归档合同见 `docs/experiments/EXECUTION_COST_B2_FROZEN.md`。

## B1 固定语义

每个本地交易日按以下顺序处理：

1. 使用已验证价格更新已持有 ETF 的估值；缺价时保留最近有效估值并记录 stale 状态。
2. 当前价格恢复时重试 pending 持仓调整。
3. 处理当日计划执行的新研究信号；信号最早在下一个有效交易日执行。
4. 记录日终 NAV、实际权重、现金、缺价资产和 pending 状态。

新信号可以 supersede 旧 pending，但旧记录必须保留在审计历史中。未持有 ETF 如果没有可用入场价格，其目标权重转为现金且不会在未来自动追单。

核心执行假设不可配置：

- transaction cost = 0
- slippage = 0
- cash yield = 0
- no borrowing
- no ETF pre-listing return
- no index-return substitution

报告中的成本和现金收益字段只是固定兼容声明，不是扩展入口。

## 请求、实际和延期状态

每个信号事件必须区分：

- `requested_target_weights`
- `executable_target_weights`
- `actual_post_trade_weights`
- `deferred_adjustments`
- `cash_breakdown`
- `reconciliation`
- `first_attempt_snapshot`
- `completion_snapshot`
- `terminal_status`

冻结持仓不能同时计入 `missing_entry_price_cash`。请求、实际、现金和延期状态必须能够独立重算。

## C0-A 合同基线

`backtest/execution/v2/contracts.py` 定义未来核心接口的冻结数据合同，但 C0-A 不接入现有运行路径，也不改变当前输出：

- `SourceManifestEntry`
- `ExecutionCoreInputs`
- `ExecutionCoreConfig`
- `ExecutionCoreResult`
- `ExecutionVersionStatus`

来源清单由外围调用方预先计算并传入。核心只验证和携带内存数据，不读取 `ROOT`、不打开路径、不调用 loader。

未来 C0-B 将拆分两个身份：

- `core_run_id`：只绑定核心输入、核心合同和核心代码，不绑定 V1。
- `artifact_run_id`：绑定 core 结果、serializer schema、可选 V1 comparison 和输出文件集合。

兼容 JSON 顶层 `run_id` 将作为 `artifact_run_id` 的别名；C0-A 不修改现有 run ID 或产物。

## B1 完整性与 golden freeze

现有 B1 输出仍通过 staging、跨文件校验、manifest 和 committed marker fail closed。`reports/execution_v2_b1_golden.json` 是不可修改的业务行为基线。

C0-B 只有在以下内容保持一致时才允许重生成 B1：

- golden business hash
- equity curve
- periods
- metrics
- coverage contract
- gap metrics
- signal 和 pending 业务语义

源码结构变化可以改变未来的 run identity、source manifest 和 output-set hash，但不能改变上述业务结果。

## 非交易边界

Execution V2 只用于决策支持和执行可用性验证。任何版本都不得输出订单、股数、金额、目标价格或自动实盘动作。
