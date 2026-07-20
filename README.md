# MyInvestTAA

MyInvestTAA 是一个离线、只读的战术资产配置（TAA）研究与决策支持系统。它使用估值、景气、趋势、情绪和宏观证据研究资产权重，并验证研究指数配置映射到可交易 ETF 后的历史差异。

系统不生成订单、股数、金额或目标价格，不连接自动实盘，也不把研究结果包装成确定性投资建议。

## 普通用户怎么用

启动 Web：

```powershell
python backend/main.py
```

浏览器打开 `http://localhost:8025/`，按以下顺序阅读：

1. **系统首页**：确认数据日期、发布状态和当前可用模块。
2. **当前配置决策**：阅读市场状态、模型权重、Research、Shadow 和执行限制的综合快照。
3. **V11 模型配置**：查看正式候选模型使用的比例权重及解释。
4. **研究与执行验证**：理解研究指数结果与真实 ETF 可执行结果之间的差异。
5. **系统与数据状态**：核查数据来源、哈希、已知限制和发布完整性。

所有页面都是只读决策支持界面。`ready` 表示证据完整可供人工审核，不表示允许直接交易。

## TAA 是什么

战略资产配置（SAA）回答“长期大致配置多少股票、债券、黄金和现金”；TAA 回答“在长期框架不失控的前提下，未来几周到一两年应该阶段性多配或少配哪些资产”。

本项目的 TAA 原则是：

- 长期配置有底座，短期调整有边界。
- 仓位用比例表达，不输出金额和股数。
- 多类证据共同支持后才调整，不追逐单条新闻。
- 数据缺失、映射近似和样本不足必须明确披露。
- 回测用于研究和比较，不等于未来收益承诺。

## 当前执行版本

| 版本 | 当前定位 | 是否正式门槛 | 是否继续扩展 |
| --- | --- | --- | --- |
| Execution V1 | 正式历史执行基线，只读维护 | 是 | 否 |
| Execution V2 B1 | 零成本执行语义的核心候选 | 否 | 仅做核心稳定与迁移评审 |
| Execution V2 B2 | 冻结的历史成本研究实验 | 否 | 否 |

V2 B1 尚未替换 V1，B2 不进入 Current Decision、Web、正式发布或核心验收。详细状态见 [执行版本生命周期](docs/EXECUTION_VERSION_LIFECYCLE.md)。

## 固定边界

核心执行语义固定为：交易成本为零、滑点为零、现金收益为零、不借款、不使用 ETF 上市前收益、不用指数收益替代 ETF 收益。

最低手续费、券商费率差异、市场冲击、复杂滑点、流动性模型、税费历史、成交量约束、真实成交模拟和自动实盘均不属于项目范围。完整清单见 [非目标](docs/NON_GOALS.md)。

## 项目文档

- [项目范围](docs/PROJECT_SCOPE.md)
- [非目标](docs/NON_GOALS.md)
- [Execution V2 语义](docs/EXECUTION_V2.md)
- [执行版本生命周期](docs/EXECUTION_VERSION_LIFECYCLE.md)
- [核心完成标准](docs/CORE_COMPLETION_CRITERIA.md)
- [B2 冻结说明](docs/experiments/EXECUTION_COST_B2_FROZEN.md)
- [系统架构](docs/ARCHITECTURE.md)
- [数据合同](docs/DATA_CONTRACTS.md)
- [数据来源](docs/DATA_SOURCES.md)
- [操作手册](docs/OPERATIONS.md)
- [已知限制](docs/LIMITATIONS.md)

## 正式发布验证

当前正式发布继续以 Execution V1 为执行依据。只读验证命令：

```powershell
python scripts/verify_system_release.py
```

需要在明确授权的发布任务中完整离线重建时，使用唯一的参数化命令：

```powershell
python scripts/build_system_release.py --market-data-as-of <最新交易日> --decision-date <决策日> --generated-at <UTC时间> --provider local --output-dir reports/release
```

C0-A 只冻结范围和合同，不执行该重建命令，也不刷新正式发布。

只有通过单独的 V1/V2 最终迁移裁决后，V2 B1 才可能进入正式门槛；C0 核心整理本身不会自动完成该切换。
