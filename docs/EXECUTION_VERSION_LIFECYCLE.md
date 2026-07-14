# 执行版本生命周期

## Execution V1

- lifecycle: `formal_legacy_execution_baseline`
- gate: `current_formal_gate_source`
- maintenance: `read_only_maintenance`
- production role: 继续作为当前正式发布的执行依据
- feature development: 不新增功能

## Execution V2 B1

- lifecycle: `core_candidate`
- semantics: `zero_cost_core_semantics`
- formal status: `not_yet_formal`
- production actionable: `false`
- eligible for final migration review: `false`
- Current Decision: 不接入
- release gate: 不接入

C0 完成后仍需单独执行 V1/V2 同口径对账和迁移裁决。未经明确批准，V1 保持正式来源。

## Execution V2 B2

- lifecycle: `frozen_archived_research_experiment`
- original B1 baseline output-set hash: `3edefb9ede72dd40bcb5416be593699306859f5f5898dce7b7778df800174615`
- current alignment required: `false`
- core acceptance member: `false`
- Current Decision member: `false`
- release gate member: `false`
- Web member: `false`
- maintenance: `archive_only`
- further development: `none`

B2 的代码和历史产物保留用于审计原始研究结论。未来 B1 身份变化后，B2 对当前 B1 返回 unavailable 是预期的归档状态，而不是要求继续修复的故障。

## 双层身份设计

C0-B 将引入：

- `core_run_id`：只绑定研究输入、ETF 价格、approved mapping、execution universe、交易日历、instrument metadata、核心配置、合同版本和核心代码身份，不包含 V1。
- `artifact_run_id`：绑定 `core_run_id`、serializer schema、comparison adapter 版本、可选 V1 identity 和输出文件集合。

兼容输出的顶层 `run_id` 保留，并作为 `artifact_run_id` 的兼容别名。加入 V1 comparison 不得改变核心结果。
