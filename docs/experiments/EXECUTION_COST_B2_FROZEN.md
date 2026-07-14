# Execution V2 B2 冻结归档

## 状态

Execution V2 B2 的生命周期状态是：

`frozen_archived_research_experiment`

它是绑定特定 B1 基线的历史成本研究快照，不是正式执行模型，也不是当前核心输出。

## 归档身份

- baseline B1 output-set hash: `3edefb9ede72dd40bcb5416be593699306859f5f5898dce7b7778df800174615`
- B2 output-set hash: `f7be8bb0358b627fab431d105f806023955d4435292245dcf7fe4ab99ea99252`
- cost policy ID: `EXECUTION_V2_COST_POLICY_V1`

## 边界

B2：

- 不属于核心验收标准。
- 不进入 Current Decision。
- 不进入正式 release gate。
- 不进入 Web 正式导航。
- 不具备 production actionable 资格。
- 不再继续修复、扩展或增加研究情景。

`B2-1-Fix2`、`B2-2`、`B2-3` 以及现金收益、高级成本、流动性和券商费率计划均已取消。

## 与未来 B1 的关系

历史 B2 产物和代码保持原样。C0-B 重生成 B1 后，如果当前 B1 output-set hash 与归档 baseline 不同，B2 loader 返回 unavailable 是正确的生命周期结果。

归档测试只需证明：

- 历史文件和身份仍存在。
- 纯成本数学单元行为没有被意外破坏。
- 归档 baseline 与当前 B1 不一致时 fail closed。

不再要求历史 B2 与未来 B1 动态对齐。
