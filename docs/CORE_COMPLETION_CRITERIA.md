# 核心完成标准

核心项目只有在以下证据全部成立后才可进入最终验收。

## 执行语义

- 信号不在信号日执行，最早在下一个有效交易日执行。
- 周末和节假日正确顺延。
- ETF 上市前不使用 ETF 收益。
- 不用指数收益填充 ETF 收益。
- 无 approved proxy 或 low-quality proxy 时权重转现金。
- 未持有且缺价时不能进入。
- 已持有且缺价时保留最近有效估值。
- 缺价调仓形成 pending，恢复日继续处理。
- 连续缺价保持 pending，新信号可 supersede 旧 pending 并保留记录。
- 同一 ETF 对应多个研究资产时权重正确聚合。

## 对账与确定性

- requested、executable、actual、cash 和 deferred 可独立重算。
- 每日权重合计为 1。
- NAV 连续、有限并可重算。
- 输入顺序不影响结果。
- 相同输入连续运行结果完全一致。
- V1 comparison 的加入或变化不影响 core result。

## 固定核心假设

- transaction cost 恒为 0。
- slippage 恒为 0。
- cash yield 恒为 0。
- 非零成本或现金收益配置必须被拒绝，不能改变核心结果。
- 核心不生成成本 ledger 或现金收益 ledger。

## 边界和架构

- 核心不产生订单、股数、金额或目标价格。
- core 模块不导入 B2 成本模块或 FastAPI。
- core 不读取文件系统，来源清单由外围传入。
- translation 不读取价格文件。
- portfolio 不了解 research asset ID。
- pending 不构建最终报告。
- analytics 不修改组合状态。
- report 只负责输出提交、读取和完整性验证。
- Current Decision 和正式 release 不依赖 B2。

## 行为保护

- B1 golden business hash 保持 `612062e915811ce6588ba276f339d819d9fe3e164127247546e262f7984e2e55`。
- B1 equity curve、periods、metrics、coverage contract、gap metrics、signal 和 pending 业务语义逐项保持。
- V1、mapping、execution gate、Current Decision、V11、Research 和 Shadow 不因核心重构改变。
- 仓库全量测试退出码为 0。

## 完成路线

核心完成要求依次通过 C0-A、C0-B、C0-C、精简 R0、V1/V2 最终迁移裁决和最终无核心 P0/P1 审核。B2 精细化、现金收益、流动性、市场冲击和券商费率验证不是完成前置条件。
