# Data Sources

## Execution ETF validation

The execution backtest uses Tushare `fund_daily` plus `fund_adj` to construct locally cached ETF qfq price histories. The cache is created only by offline scripts and the Web/API reads generated reports only.

ETF history starts at the actual first returned trading date. The project does not stitch index and ETF history, use ETF prices before ETF inception, or use index prices to fill missing ETF dates.

The research-index backtest and ETF execution backtest are separate validations. Neither is a production trading instruction.
