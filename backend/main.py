from __future__ import annotations

from html import escape
import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.benchmark import compare_strategies
from backtest.evaluation import rolling_analysis
from backtest.simulator import run_sample_backtest
from backtest.taa import run_taa_backtest
from data_pipeline import (
    build_full_validation_report,
    build_real_performance_report,
    build_strategy_diagnosis_report,
    build_validated_performance_report,
    run_live_backtest_report,
)
from engine.allocation import build_allocation_recommendation
from engine.asset_repository import load_assets, load_price_history
from engine.anchor import load_anchor_profiles
from engine.attribution import analyze_attribution
from engine.data_quality import build_quality_summary
from engine.drawdown import calculate_drawdown, calculate_drawdown_percentile, detect_drawdown_events
from engine.opportunity import build_opportunity_ranking
from engine.recovery import analyze_recovery_events
from engine.regime import detect_market_regime
from engine.risk import build_risk_budget
from engine.taa_score import build_taa_ranking
from storage import MarketDataRepository, connect_database


app = FastAPI(
    title="MyInvestTAA",
    description="Tactical Asset Allocation MVP with drawdown and anchor scoring.",
    version="0.1.0",
)


@app.get("/api/assets")
def get_assets() -> list[dict]:
    return load_assets()


@app.get("/api/taa/ranking")
def get_taa_ranking() -> list[dict]:
    return build_taa_ranking(load_assets())


@app.get("/api/drawdown/events/{asset_id}")
def get_drawdown_events(asset_id: str) -> dict:
    history = load_price_history(asset_id)
    events = detect_drawdown_events(history)
    closes = [float(row["close"]) for row in history]
    current = calculate_drawdown(closes)
    pressure = calculate_drawdown_percentile(events, current.current_drawdown_pct)
    return {
        "asset_id": asset_id,
        "events": [event.as_dict() for event in events],
        "current_pressure": pressure,
    }


@app.get("/api/backtest/sample")
def get_sample_backtest() -> dict:
    return run_sample_backtest()


@app.get("/api/backtest/taa")
def get_taa_backtest() -> dict:
    return run_taa_backtest()


@app.get("/api/backtest/comparison")
def get_backtest_comparison() -> dict:
    return compare_strategies()


@app.get("/api/research/evaluation")
def get_research_evaluation() -> dict:
    return rolling_analysis()


@app.get("/api/research/quality")
def get_research_quality() -> dict:
    return build_quality_summary()


@app.get("/api/research/attribution")
def get_research_attribution() -> dict:
    return analyze_attribution()


@app.get("/api/research/live-backtest")
def get_live_backtest() -> dict:
    return _build_live_backtest_report()


@app.get("/api/research/real-performance")
def get_real_performance() -> dict:
    return _build_real_performance_report()


@app.get("/api/research/validated-performance")
def get_validated_performance() -> dict:
    return _build_validated_performance_report()


@app.get("/api/research/full-validation")
def get_full_validation() -> dict:
    return _build_full_validation_report()


@app.get("/api/research/diagnosis")
def get_strategy_diagnosis() -> dict:
    return _build_strategy_diagnosis_report()


@app.get("/api/recovery/{asset_id}")
def get_recovery(asset_id: str) -> dict:
    history = load_price_history(asset_id)
    events = detect_drawdown_events(history)
    return analyze_recovery_events(events, history, asset_id=asset_id).as_dict()


@app.get("/api/opportunity/ranking")
def get_opportunity_ranking() -> list[dict]:
    return build_opportunity_ranking(load_assets())


@app.get("/api/anchor/profiles")
def get_anchor_profiles() -> list[dict]:
    return [profile.as_dict() for profile in load_anchor_profiles().values()]


@app.get("/api/allocation/recommendation")
def get_allocation_recommendation() -> dict:
    return build_allocation_recommendation(load_assets()).as_dict()


@app.get("/api/regime/current")
def get_current_regime() -> dict:
    return detect_market_regime(load_price_history("510300")).as_dict()


@app.get("/api/risk/budget")
def get_risk_budget() -> dict:
    regime = detect_market_regime(load_price_history("510300"))
    return build_risk_budget(regime).as_dict()


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    ranking = build_taa_ranking(load_assets())
    regime = detect_market_regime(load_price_history("510300"))
    budget = build_risk_budget(regime)
    rows = "\n".join(
        f"""
        <tr>
          <td><strong>{item["name"]}</strong><span>{item["id"]}</span></td>
          <td>{item["category"]}</td>
          <td>{item["drawdown"]["current_drawdown_pct"]:.1f}%</td>
          <td>{item["drawdown_score"]:.1f}</td>
          <td>{item["anchor_score"]:.1f}<span>{item["anchor_level"]}</span></td>
          <td>{item["placeholder_score"]:.1f}</td>
          <td><strong>{item["taa_score"]:.1f}</strong></td>
          <td><span class="badge {item["recommendation"]}">{item["recommendation"]}</span></td>
        </tr>
        """
        for item in ranking
    )
    event_rows = "\n".join(_drawdown_history_rows(ranking))
    opportunity_rows = "\n".join(_opportunity_rows())
    allocation_rows = "\n".join(_allocation_rows())
    comparison = compare_strategies()
    comparison_rows = "\n".join(_comparison_rows(comparison))
    comparison_curve = _comparison_curve_svg(comparison)
    taa_backtest = run_taa_backtest()
    taa_metrics = taa_backtest["metrics"]

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Dashboard</title>
      <style>
        :root {{
          color-scheme: light;
          --bg: #f6f7f9;
          --panel: #ffffff;
          --text: #1d2433;
          --muted: #5f6b7a;
          --line: #d8dee8;
          --accent: #2563eb;
          --good: #0f766e;
          --watch: #b45309;
          --risk: #b91c1c;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          background: var(--bg);
          color: var(--text);
          font-family: Arial, "Microsoft YaHei", sans-serif;
        }}
        header {{
          background: var(--panel);
          border-bottom: 1px solid var(--line);
          padding: 22px 32px 18px;
        }}
        main {{
          max-width: 1180px;
          margin: 0 auto;
          padding: 26px 24px 40px;
        }}
        h1 {{
          margin: 0 0 8px;
          font-size: 26px;
          font-weight: 700;
          letter-spacing: 0;
        }}
        p {{
          margin: 0;
          color: var(--muted);
          line-height: 1.6;
        }}
        .summary {{
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 14px;
          margin-bottom: 18px;
        }}
        .metric {{
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 16px;
        }}
        .metric label {{
          display: block;
          color: var(--muted);
          font-size: 13px;
          margin-bottom: 8px;
        }}
        .metric strong {{
          display: block;
          font-size: 22px;
        }}
        table {{
          width: 100%;
          border-collapse: collapse;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          overflow: hidden;
        }}
        .history {{
          margin-top: 22px;
        }}
        h2 {{
          margin: 0 0 12px;
          font-size: 20px;
          letter-spacing: 0;
        }}
        th, td {{
          padding: 13px 14px;
          border-bottom: 1px solid var(--line);
          text-align: left;
          vertical-align: middle;
          font-size: 14px;
        }}
        th {{
          background: #eef2f7;
          color: #344054;
          font-weight: 700;
        }}
        td span {{
          display: block;
          color: var(--muted);
          font-size: 12px;
          margin-top: 4px;
        }}
        tr:last-child td {{ border-bottom: 0; }}
        .badge {{
          display: inline-block;
          min-width: 92px;
          padding: 5px 9px;
          border-radius: 999px;
          color: #fff;
          text-align: center;
          font-size: 12px;
          margin: 0;
        }}
        .curve-chart {{
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 12px;
          overflow-x: auto;
        }}
        .curve-chart svg {{
          display: block;
          width: 100%;
          min-width: 760px;
          height: auto;
        }}
        .overweight {{ background: var(--good); }}
        .watch_overweight {{ background: var(--accent); }}
        .neutral {{ background: var(--watch); }}
        .underweight, .avoid {{ background: var(--risk); }}
        @media (max-width: 820px) {{
          header {{ padding: 18px 18px 14px; }}
          main {{ padding: 18px 12px 28px; }}
          .summary {{ grid-template-columns: 1fr; }}
          table {{ display: block; overflow-x: auto; }}
          th, td {{ white-space: nowrap; }}
        }}
      </style>
    </head>
    <body>
      <header>
        <h1>MyInvestTAA Dashboard</h1>
        <p>Drawdown + Asset Anchor MVP. 输出为资产配置研究权重信号，不是交易指令。<a href="/research">Research Report</a> · <a href="/pipeline">Data Pipeline</a> · <a href="/real-research">Real Market Research</a> · <a href="/validation">Validation Report</a> · <a href="/experiment">Experiment Report</a> · <a href="/diagnosis">Strategy Diagnosis</a></p>
      </header>
      <main>
        <section class="summary" aria-label="summary">
          <div class="metric"><label>资产数量</label><strong>{len(ranking)}</strong></div>
          <div class="metric"><label>最高 TAA Score</label><strong>{ranking[0]["taa_score"]:.1f}</strong></div>
          <div class="metric"><label>市场状态</label><strong>{regime.state}</strong></div>
          <div class="metric"><label>权益上限</label><strong>{budget.equity_limit:.0f}%</strong></div>
          <div class="metric"><label>最低现金</label><strong>{budget.min_cash:.0f}%</strong></div>
          <div class="metric"><label>服务端口</label><strong>8025</strong></div>
        </section>
        <table>
          <thead>
            <tr>
              <th>资产</th>
              <th>类别</th>
              <th>当前回撤</th>
              <th>回撤评分</th>
              <th>资产锚</th>
              <th>占位评分</th>
              <th>TAA Score</th>
              <th>配置状态</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        <section class="history">
          <h2>Drawdown History</h2>
          <table>
            <thead>
              <tr>
                <th>资产</th>
                <th>历史事件数</th>
                <th>最深回撤</th>
                <th>当前压力分位</th>
                <th>压力区</th>
                <th>样例回测</th>
              </tr>
            </thead>
            <tbody>{event_rows}</tbody>
          </table>
        </section>
        <section class="history">
          <h2>Recovery Analysis</h2>
          <table>
            <thead>
              <tr>
                <th>资产</th>
                <th>压力</th>
                <th>压力区</th>
                <th>恢复概率</th>
                <th>资产锚</th>
                <th>机会评分</th>
                <th>置信调整</th>
                <th>3年中位收益</th>
              </tr>
            </thead>
          <tbody>{opportunity_rows}</tbody>
          </table>
        </section>
        <section class="history">
          <h2>Allocation Recommendation</h2>
          <table>
            <thead>
              <tr>
                <th>资产</th>
                <th>机会分</th>
                <th>建议权重</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>{allocation_rows}</tbody>
          </table>
        </section>
        <section class="history">
          <h2>TAA Backtest</h2>
          <table>
            <thead>
              <tr>
                <th>周期</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>Calmar</th>
                <th>换手</th>
                <th>期末净值</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{taa_backtest["period"]["start"]} - {taa_backtest["period"]["end"]}</td>
                <td>{taa_metrics["annual_return"]:.2f}%</td>
                <td>{taa_metrics["max_drawdown"]:.2f}%</td>
                <td>{taa_metrics["sharpe"]:.2f}</td>
                <td>{taa_metrics["calmar"]:.2f}</td>
                <td>{taa_metrics["turnover"]:.2f}</td>
                <td>{taa_metrics["ending_value"]:.4f}</td>
              </tr>
            </tbody>
          </table>
        </section>
        <section class="history">
          <h2>Strategy Comparison</h2>
          <table>
            <thead>
              <tr>
                <th>策略</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>超额收益</th>
                <th>回撤改善</th>
                <th>期末净值</th>
              </tr>
            </thead>
            <tbody>{comparison_rows}</tbody>
          </table>
        </section>
        <section class="history">
          <h2>收益曲线对比</h2>
          {comparison_curve}
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/research", response_class=HTMLResponse)
def research_report() -> str:
    comparison = compare_strategies()
    evaluation = rolling_analysis(comparison)
    strategy = comparison["strategies"]["MyInvestTAA"]
    benchmark_rows = "\n".join(_comparison_rows(comparison))
    rolling_rows = "\n".join(_rolling_rows(evaluation))
    risk_rows = "\n".join(_risk_rows(comparison))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Research Report</title>
      <style>
        :root {{
          color-scheme: light;
          --bg: #f6f7f9;
          --panel: #ffffff;
          --text: #1d2433;
          --muted: #5f6b7a;
          --line: #d8dee8;
          --accent: #2563eb;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          background: var(--bg);
          color: var(--text);
          font-family: Arial, "Microsoft YaHei", sans-serif;
        }}
        header {{
          background: var(--panel);
          border-bottom: 1px solid var(--line);
          padding: 22px 32px 18px;
        }}
        main {{
          max-width: 1180px;
          margin: 0 auto;
          padding: 26px 24px 40px;
        }}
        h1 {{ margin: 0 0 8px; font-size: 26px; letter-spacing: 0; }}
        h2 {{ margin: 24px 0 12px; font-size: 20px; letter-spacing: 0; }}
        p {{ margin: 0; color: var(--muted); line-height: 1.6; }}
        a {{ color: var(--accent); }}
        .summary {{
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 14px;
        }}
        .metric {{
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 16px;
        }}
        .metric label {{ display: block; color: var(--muted); font-size: 13px; margin-bottom: 8px; }}
        .metric strong {{ display: block; font-size: 22px; }}
        table {{
          width: 100%;
          border-collapse: collapse;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          overflow: hidden;
        }}
        th, td {{
          padding: 13px 14px;
          border-bottom: 1px solid var(--line);
          text-align: left;
          vertical-align: middle;
          font-size: 14px;
        }}
        th {{ background: #eef2f7; color: #344054; font-weight: 700; }}
        td span {{ display: block; color: var(--muted); font-size: 12px; margin-top: 4px; }}
        tr:last-child td {{ border-bottom: 0; }}
        @media (max-width: 820px) {{
          header {{ padding: 18px 18px 14px; }}
          main {{ padding: 18px 12px 28px; }}
          .summary {{ grid-template-columns: 1fr; }}
          table {{ display: block; overflow-x: auto; }}
          th, td {{ white-space: nowrap; }}
        }}
      </style>
    </head>
    <body>
      <header>
        <h1>Research Report</h1>
        <p>真实数据接口已预留，当前报告仍基于 MockProvider 样例数据。<a href="/">Dashboard</a> · <a href="/pipeline">Data Pipeline</a> · <a href="/quality">Data Quality</a> · <a href="/attribution">Attribution</a></p>
      </header>
      <main>
        <section class="summary" aria-label="strategy performance">
          <div class="metric"><label>策略</label><strong>{strategy["name"]}</strong></div>
          <div class="metric"><label>年化收益</label><strong>{strategy["annual_return"]:.2f}%</strong></div>
          <div class="metric"><label>最大回撤</label><strong>{strategy["max_drawdown"]:.2f}%</strong></div>
          <div class="metric"><label>Rolling胜率</label><strong>{evaluation["rolling_win_rate"] * 100:.1f}%</strong></div>
        </section>
        <section>
          <h2>Benchmark比较</h2>
          <table>
            <thead>
              <tr>
                <th>策略</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>超额收益</th>
                <th>回撤改善</th>
                <th>期末净值</th>
              </tr>
            </thead>
            <tbody>{benchmark_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Rolling胜率</h2>
          <table>
            <thead>
              <tr>
                <th>窗口</th>
                <th>观测数</th>
                <th>胜率</th>
                <th>平均Alpha</th>
                <th>中位Alpha</th>
                <th>回撤改善概率</th>
              </tr>
            </thead>
            <tbody>{rolling_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>风险指标</h2>
          <table>
            <thead>
              <tr>
                <th>策略</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>回撤改善</th>
                <th>Sharpe差异</th>
              </tr>
            </thead>
            <tbody>{risk_rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/pipeline", response_class=HTMLResponse)
def data_pipeline_page() -> str:
    report = _build_live_backtest_report()
    quality = report["quality"]
    metrics = report["backtest"]["metrics"]

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Data Pipeline</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Data Pipeline</h1>
        <p>Provider → Normalizer → Quality → Database → Backtest。<a href="/research">Research Report</a></p>
      </header>
      <main>
        <section>
          <h2>导入状态</h2>
          <table>
            <tbody>
              <tr><td>数据源</td><td>{report["data_source"]}</td></tr>
              <tr><td>更新时间</td><td>{report["updated_at"]}</td></tr>
              <tr><td>资产数量</td><td>{report["asset_count"]}</td></tr>
              <tr><td>价格行数</td><td>{report["price_rows"]}</td></tr>
              <tr><td>质量评分</td><td>{quality["average_score"]:.2f}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>真实回测报告</h2>
          <table>
            <tbody>
              <tr><td>策略</td><td>{report["backtest"]["strategy"]}</td></tr>
              <tr><td>回测周期</td><td>{report["backtest"]["period"]["start"]} - {report["backtest"]["period"]["end"]}</td></tr>
              <tr><td>年化收益</td><td>{metrics["annual_return"]:.2f}%</td></tr>
              <tr><td>最大回撤</td><td>{metrics["max_drawdown"]:.2f}%</td></tr>
              <tr><td>Sharpe</td><td>{metrics["sharpe"]:.2f}</td></tr>
              <tr><td>归因主导因子</td><td>{report["attribution"]["dominant_factor"]}</td></tr>
            </tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/real-research", response_class=HTMLResponse)
def real_market_research_page() -> str:
    report = _build_real_performance_report()
    data = report["data"]
    performance = report["performance"]
    benchmark_rows = "\n".join(_real_benchmark_rows(report["benchmark"]))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Real Market Research</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Real Market Research</h1>
        <p>真实 A 股研究工作流入口，当前默认用 MockProvider 跑完整管道。<a href="/pipeline">Data Pipeline</a></p>
      </header>
      <main>
        <section>
          <h2>数据</h2>
          <table>
            <tbody>
              <tr><td>数据源</td><td>{data["provider"]}</td></tr>
              <tr><td>周期</td><td>{data["dataset_version"]["start_date"]} - {data["dataset_version"]["end_date"]}</td></tr>
              <tr><td>ETF Universe</td><td>{data["universe_asset_count"]} ETFs</td></tr>
              <tr><td>导入资产</td><td>{data["imported_asset_count"]}</td></tr>
              <tr><td>质量评分</td><td>{data["quality_score"]:.2f}</td></tr>
              <tr><td>Dataset Version</td><td>{data["dataset_version"]["dataset_id"]}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>策略表现</h2>
          <table>
            <tbody>
              <tr><td>年化收益</td><td>{performance["annual_return"]:.2f}%</td></tr>
              <tr><td>最大回撤</td><td>{performance["max_drawdown"]:.2f}%</td></tr>
              <tr><td>Sharpe</td><td>{performance["sharpe"]:.2f}</td></tr>
              <tr><td>Calmar</td><td>{performance["calmar"]:.2f}</td></tr>
              <tr><td>Rolling Alpha</td><td>{report["stability"]["rolling_alpha"]:.2f}%</td></tr>
              <tr><td>Win Rate</td><td>{report["stability"]["win_rate"] * 100:.1f}%</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Benchmark</h2>
          <table>
            <thead>
              <tr>
                <th>策略</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>超额收益</th>
              </tr>
            </thead>
            <tbody>{benchmark_rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/validation", response_class=HTMLResponse)
def validation_report_page() -> str:
    report = _build_validated_performance_report()
    dataset = report["dataset"]
    performance = report["performance"]
    attribution_rows = "\n".join(_performance_attribution_rows(report["attribution"]["performance"]))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Validation Report</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Validation Report</h1>
        <p>Real Data Validation 入口。当前默认用 MockProvider，Tushare 验证脚本已提供。<a href="/real-research">Real Market Research</a></p>
      </header>
      <main>
        <section>
          <h2>Real Data Validation</h2>
          <table>
            <tbody>
              <tr><td>Source</td><td>{dataset["provider"]}</td></tr>
              <tr><td>Period</td><td>{dataset["dataset_version"]["start_date"]} - {dataset["dataset_version"]["end_date"]}</td></tr>
              <tr><td>Assets</td><td>{dataset["imported_asset_count"]}</td></tr>
              <tr><td>Quality</td><td>{dataset["quality_score"]:.2f}</td></tr>
              <tr><td>Dataset</td><td>{dataset["dataset_version"]["dataset_id"]}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Performance</h2>
          <table>
            <tbody>
              <tr><td>Annual Return</td><td>{performance["annual_return"]:.2f}%</td></tr>
              <tr><td>Max Drawdown</td><td>{performance["max_drawdown"]:.2f}%</td></tr>
              <tr><td>Sharpe</td><td>{performance["sharpe"]:.2f}</td></tr>
              <tr><td>Calmar</td><td>{performance["calmar"]:.2f}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Contribution</h2>
          <table>
            <thead>
              <tr>
                <th>资产</th>
                <th>收益贡献</th>
              </tr>
            </thead>
            <tbody>{attribution_rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/experiment", response_class=HTMLResponse)
def experiment_report_page() -> str:
    report = _build_full_validation_report()
    dataset = report["dataset"]
    experiment = report["experiment"]
    performance = report["performance"]
    benchmark_rows = "\n".join(_full_validation_benchmark_rows(report["benchmark"]["rows"]))
    contribution_rows = "\n".join(_full_validation_contribution_rows(report["attribution"]["top_contributors"]))
    regime_rows = "\n".join(_regime_contribution_rows(report["attribution"]["regime_contribution"]))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Experiment Report</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Experiment Report</h1>
        <p>Full Validation 研究实验报告。默认使用 MockProvider，真实长周期验证请运行脚本。<a href="/validation">Validation Report</a></p>
      </header>
      <main>
        <section>
          <h2>Experiment</h2>
          <table>
            <tbody>
              <tr><td>Experiment ID</td><td>{experiment["experiment_id"]}</td></tr>
              <tr><td>Dataset</td><td>{dataset["dataset_id"]}</td></tr>
              <tr><td>Config Hash</td><td>{experiment["config_hash"]}</td></tr>
              <tr><td>Return Type</td><td>{dataset["return_type"]}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Dataset</h2>
          <table>
            <tbody>
              <tr><td>Provider</td><td>{dataset["provider"]}</td></tr>
              <tr><td>Period</td><td>{dataset["period"]["start"]} - {dataset["period"]["end"]}</td></tr>
              <tr><td>Assets</td><td>{dataset["asset_count"]}</td></tr>
              <tr><td>Rows</td><td>{dataset["rows"]}</td></tr>
              <tr><td>Quality</td><td>{dataset["quality_score"]:.2f}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Performance</h2>
          <table>
            <tbody>
              <tr><td>Annual Return</td><td>{performance["annual_return"]:.2f}%</td></tr>
              <tr><td>Max Drawdown</td><td>{performance["max_drawdown"]:.2f}%</td></tr>
              <tr><td>Sharpe</td><td>{performance["sharpe"]:.2f}</td></tr>
              <tr><td>Calmar</td><td>{performance["calmar"]:.2f}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Benchmark</h2>
          <table>
            <thead>
              <tr>
                <th>策略</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>Alpha</th>
                <th>回撤改善</th>
              </tr>
            </thead>
            <tbody>{benchmark_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Attribution</h2>
          <table>
            <thead><tr><th>资产</th><th>贡献</th></tr></thead>
            <tbody>{contribution_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Regime Contribution</h2>
          <table>
            <thead><tr><th>状态</th><th>贡献</th></tr></thead>
            <tbody>{regime_rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/quality", response_class=HTMLResponse)
def data_quality_page() -> str:
    summary = build_quality_summary()
    rows = "\n".join(_quality_rows(summary))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Data Quality</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Data Quality</h1>
        <p>数据源：{summary["source"]}，平均质量评分 {summary["average_score"]:.1f}。<a href="/research">Research Report</a></p>
      </header>
      <main>
        <section>
          <h2>数据质量评分</h2>
          <table>
            <thead>
              <tr>
                <th>资产</th>
                <th>评分</th>
                <th>行数</th>
                <th>缺失天数</th>
                <th>重复行</th>
                <th>非法价格</th>
                <th>异常跳变</th>
                <th>警告</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/diagnosis", response_class=HTMLResponse)
def strategy_diagnosis_page() -> str:
    report = _build_strategy_diagnosis_report()
    dataset = report["dataset"]
    issues = "\n".join(_diagnosis_issue_rows(report["diagnosis"]["summary"]))
    version_rows = "\n".join(_diagnosis_version_rows(report["versions"]["rows"]))
    regime_rows = "\n".join(_diagnosis_regime_rows(report["diagnosis"]["regime_analysis"]["regimes"]))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Strategy Diagnosis</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Strategy Diagnosis</h1>
        <p>诊断当前 TAA 策略弱点并比较 V1/V2/V3。<a href="/experiment">Experiment Report</a></p>
      </header>
      <main>
        <section>
          <h2>Dataset</h2>
          <table>
            <tbody>
              <tr><td>Provider</td><td>{dataset["provider"]}</td></tr>
              <tr><td>Period</td><td>{dataset["period"]["start"]} - {dataset["period"]["end"]}</td></tr>
              <tr><td>Assets</td><td>{dataset["asset_count"]}</td></tr>
              <tr><td>Return Type</td><td>{dataset["return_type"]}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>主要损失来源</h2>
          <table>
            <thead><tr><th>来源</th><th>严重性</th><th>证据</th></tr></thead>
            <tbody>{issues}</tbody>
          </table>
        </section>
        <section>
          <h2>Version Comparison</h2>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>Calmar</th>
                <th>期末净值</th>
              </tr>
            </thead>
            <tbody>{version_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Regime Analysis</h2>
          <table>
            <thead>
              <tr>
                <th>状态</th>
                <th>期数</th>
                <th>平均收益</th>
                <th>平均权益暴露</th>
                <th>配置影响</th>
              </tr>
            </thead>
            <tbody>{regime_rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/attribution", response_class=HTMLResponse)
def attribution_page() -> str:
    report = analyze_attribution()
    rows = "\n".join(_attribution_rows(report))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Attribution</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Attribution</h1>
        <p>第一版为 Score Attribution，主导因子：{report["dominant_factor"]}。<a href="/research">Research Report</a></p>
      </header>
      <main>
        <section>
          <h2>收益来源</h2>
          <table>
            <thead>
              <tr>
                <th>因子</th>
                <th>贡献</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
        <section>
          <h2>说明</h2>
          <table>
            <tbody>
              <tr><td>观测次数</td><td>{report["observations"]}</td></tr>
              <tr><td>解释边界</td><td>{"; ".join(report["notes"])}</td></tr>
            </tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


def _drawdown_history_rows(ranking: list[dict]) -> list[str]:
    rows: list[str] = []
    sample_backtest = run_sample_backtest()
    for item in ranking:
        history = load_price_history(item["id"])
        events = detect_drawdown_events(history)
        current = calculate_drawdown([float(row["close"]) for row in history])
        pressure = calculate_drawdown_percentile(events, current.current_drawdown_pct)
        worst = min((event.drawdown_pct for event in events), default=0.0)
        backtest_text = (
            f"{sample_backtest['annual_return']:.1f}% annual / "
            f"{sample_backtest['max_drawdown']:.1f}% DD"
            if item["id"] == sample_backtest["asset_id"]
            else "-"
        )
        rows.append(
            f"""
            <tr>
              <td><strong>{item["name"]}</strong><span>{item["id"]}</span></td>
              <td>{len(events)}</td>
              <td>{worst:.1f}%</td>
              <td>{pressure["percentile"]:.2f}</td>
              <td>{pressure["zone"]}</td>
              <td>{backtest_text}</td>
            </tr>
            """
        )
    return rows


def _opportunity_rows() -> list[str]:
    rows: list[str] = []
    for item in build_opportunity_ranking(load_assets()):
        forward_3y = item["median_forward_return_3y_pct"]
        forward_text = f"{forward_3y:.1f}%" if forward_3y is not None else "insufficient"
        rows.append(
            f"""
            <tr>
              <td><strong>{item["name"]}</strong><span>{item["id"]}</span></td>
              <td>{item["drawdown_pressure"]:.1f}</td>
              <td>{item["pressure_zone"]}</td>
              <td>{item["recovery_probability"]:.1f}%</td>
              <td>{item["anchor_score"]:.1f}</td>
              <td><strong>{item["opportunity_score"]:.1f}</strong></td>
              <td>{item["confidence_adjusted_score"]:.1f}</td>
              <td>{forward_text}</td>
            </tr>
            """
        )
    return rows


def _allocation_rows() -> list[str]:
    recommendation = build_allocation_recommendation(load_assets())
    rows: list[str] = []
    for item in recommendation.allocation:
        score_text = "-" if item.opportunity_score is None else f"{item.opportunity_score:.1f}"
        rows.append(
            f"""
            <tr>
              <td><strong>{item.name}</strong><span>{item.asset_id}</span></td>
              <td>{score_text}</td>
              <td>{item.weight:.1f}%</td>
              <td>{item.status}</td>
            </tr>
            """
        )
    return rows


def _comparison_rows(comparison: dict) -> list[str]:
    rows: list[str] = []
    for item in comparison["rows"]:
        rows.append(
            f"""
            <tr>
              <td><strong>{item["name"]}</strong><span>{item["strategy_id"]}</span></td>
              <td>{item["annual_return"]:.2f}%</td>
              <td>{item["max_drawdown"]:.2f}%</td>
              <td>{item["sharpe"]:.2f}</td>
              <td>{item["excess_return"]:.2f}%</td>
              <td>{item["drawdown_improvement"]:.2f}%</td>
              <td>{item["ending_value"]:.4f}</td>
            </tr>
            """
        )
    return rows


def _comparison_curve_svg(comparison: dict) -> str:
    curves = comparison["equity_curves"]
    all_values = [
        float(point["value"])
        for curve in curves.values()
        for point in curve
    ]
    if not all_values:
        return '<div class="curve-chart"><p>暂无曲线数据</p></div>'

    width = 900
    height = 260
    left = 48
    right = 20
    top = 18
    bottom = 42
    plot_width = width - left - right
    plot_height = height - top - bottom
    min_value = min(all_values)
    max_value = max(all_values)
    if min_value == max_value:
        min_value -= 0.01
        max_value += 0.01

    colors = {
        "MyInvestTAA": "#2563eb",
        "HS300_BUY_HOLD": "#b45309",
        "SAA_60_40": "#0f766e",
        "EQUAL_WEIGHT": "#b91c1c",
    }
    names = {
        item["strategy_id"]: item["name"]
        for item in comparison["rows"]
    }

    def point_xy(index: int, count: int, value: float) -> tuple[float, float]:
        x = left + (plot_width * index / max(count - 1, 1))
        y = top + plot_height * (max_value - value) / (max_value - min_value)
        return round(x, 2), round(y, 2)

    polylines: list[str] = []
    legends: list[str] = []
    for legend_index, (strategy_id, curve) in enumerate(curves.items()):
        points = " ".join(
            f"{x},{y}"
            for x, y in (
                point_xy(index, len(curve), float(point["value"]))
                for index, point in enumerate(curve)
            )
        )
        color = colors.get(strategy_id, "#344054")
        polylines.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" '
            f'stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round" />'
        )
        legend_x = left + legend_index * 196
        legends.append(
            f'<g><line x1="{legend_x}" y1="238" x2="{legend_x + 22}" y2="238" '
            f'stroke="{color}" stroke-width="2.6" />'
            f'<text x="{legend_x + 28}" y="242" font-size="12" fill="#344054">'
            f'{escape(names.get(strategy_id, strategy_id))}</text></g>'
        )

    grid_values = [min_value, (min_value + max_value) / 2.0, max_value]
    grid_lines = []
    for value in grid_values:
        _, y = point_xy(0, 2, value)
        grid_lines.append(
            f'<line x1="{left}" y1="{y}" x2="{width - right}" y2="{y}" '
            f'stroke="#d8dee8" stroke-width="1" />'
            f'<text x="8" y="{y + 4}" font-size="11" fill="#5f6b7a">{value:.2f}</text>'
        )

    return f"""
    <div class="curve-chart">
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="收益曲线对比">
        <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
        {"".join(grid_lines)}
        <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#98a2b3" stroke-width="1" />
        <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#98a2b3" stroke-width="1" />
        {"".join(polylines)}
        {"".join(legends)}
      </svg>
    </div>
    """


def _rolling_rows(evaluation: dict) -> list[str]:
    rows: list[str] = []
    for item in evaluation["windows"]:
        primary = item["benchmarks"].get(evaluation["primary_benchmark"], {})
        rows.append(
            f"""
            <tr>
              <td>{item["rolling_period"]}</td>
              <td>{primary.get("observations", 0)}</td>
              <td>{item["rolling_win_rate"] * 100:.1f}%</td>
              <td>{item["avg_alpha"]:.2f}%</td>
              <td>{primary.get("median_alpha", 0.0):.2f}%</td>
              <td>{primary.get("positive_drawdown_improvement_rate", 0.0) * 100:.1f}%</td>
            </tr>
            """
        )
    return rows


def _risk_rows(comparison: dict) -> list[str]:
    rows: list[str] = []
    for item in comparison["rows"]:
        rows.append(
            f"""
            <tr>
              <td><strong>{item["name"]}</strong><span>{item["strategy_id"]}</span></td>
              <td>{item["max_drawdown"]:.2f}%</td>
              <td>{item["sharpe"]:.2f}</td>
              <td>{item["drawdown_improvement"]:.2f}%</td>
              <td>{item["sharpe_difference"]:.2f}</td>
            </tr>
            """
        )
    return rows


def _quality_rows(summary: dict) -> list[str]:
    rows: list[str] = []
    for item in summary["reports"]:
        warning_text = "; ".join(item["warnings"]) if item["warnings"] else "-"
        rows.append(
            f"""
            <tr>
              <td><strong>{item["asset_id"]}</strong></td>
              <td>{item["score"]:.1f}</td>
              <td>{item["row_count"]}</td>
              <td>{item["missing_days"]}</td>
              <td>{item["duplicate_rows"]}</td>
              <td>{item["invalid_prices"]}</td>
              <td>{item["abnormal_jumps"]}</td>
              <td>{escape(warning_text)}</td>
            </tr>
            """
        )
    return rows


def _attribution_rows(report: dict) -> list[str]:
    rows: list[str] = []
    labels = {
        "drawdown": "Drawdown Factor",
        "recovery": "Recovery Factor",
        "anchor": "Anchor Factor",
        "regime": "Regime Control",
        "allocation": "Allocation/Rebalance",
    }
    for key, value in report["contribution"].items():
        rows.append(
            f"""
            <tr>
              <td>{labels.get(key, key)}</td>
              <td>{value:.2f}%</td>
            </tr>
            """
        )
    return rows


def _real_benchmark_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td><strong>{item["name"]}</strong><span>{item["strategy_id"]}</span></td>
              <td>{item["annual_return"]:.2f}%</td>
              <td>{item["max_drawdown"]:.2f}%</td>
              <td>{item["sharpe"]:.2f}</td>
              <td>{item["excess_return"]:.2f}%</td>
            </tr>
            """
        )
    return html_rows


def _performance_attribution_rows(report: dict) -> list[str]:
    rows: list[str] = []
    for item in report["top_contributors"]:
        rows.append(
            f"""
            <tr>
              <td>{item["asset_id"]}</td>
              <td>{item["contribution"]:.2f}%</td>
            </tr>
            """
        )
    return rows


def _full_validation_benchmark_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td><strong>{item["name"]}</strong><span>{item["strategy_id"]}</span></td>
              <td>{item["annual_return"]:.2f}%</td>
              <td>{item["max_drawdown"]:.2f}%</td>
              <td>{item["sharpe"]:.2f}</td>
              <td>{item["excess_return"]:.2f}%</td>
              <td>{item["drawdown_improvement"]:.2f}%</td>
            </tr>
            """
        )
    return html_rows


def _full_validation_contribution_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{item["asset_id"]}</td>
              <td>{item["contribution"]:.2f}%</td>
            </tr>
            """
        )
    return html_rows


def _regime_contribution_rows(report: dict) -> list[str]:
    rows: list[str] = []
    for regime, contribution in report["contribution"].items():
        rows.append(
            f"""
            <tr>
              <td>{regime}</td>
              <td>{contribution:.2f}%</td>
            </tr>
            """
        )
    return rows


def _diagnosis_issue_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return "<tr><td colspan=\"3\">No major issue detected</td></tr>"
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item["source"]))}</td>
              <td>{escape(str(item["severity"]))}</td>
              <td>{escape(str(item["evidence"]))}</td>
            </tr>
            """
        )
    return html_rows


def _diagnosis_version_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{item["version"]}</td>
              <td>{item["annual_return"]:.2f}%</td>
              <td>{item["max_drawdown"]:.2f}%</td>
              <td>{item["sharpe"]:.2f}</td>
              <td>{item["calmar"]:.2f}</td>
              <td>{item["ending_value"]:.4f}</td>
            </tr>
            """
        )
    return html_rows


def _diagnosis_regime_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{item["state"]}</td>
              <td>{item["periods"]}</td>
              <td>{item["avg_return"]:.2f}%</td>
              <td>{item["avg_equity_exposure"]:.2f}%</td>
              <td>{item["allocation_effect"]:.2f}%</td>
            </tr>
            """
        )
    return html_rows


def _build_live_backtest_report() -> dict:
    connection = connect_database(":memory:")
    repository = MarketDataRepository(connection)
    return run_live_backtest_report(repository, provider_name="mock")


def _build_real_performance_report() -> dict:
    connection = connect_database(":memory:")
    repository = MarketDataRepository(connection)
    return build_real_performance_report(repository, provider_name="mock")


def _build_validated_performance_report() -> dict:
    connection = connect_database(":memory:")
    repository = MarketDataRepository(connection)
    return build_validated_performance_report(repository, provider_name="mock")


def _build_full_validation_report() -> dict:
    report_path = ROOT / "reports" / "full_validation_report.json"
    if report_path.exists():
        return json.loads(report_path.read_text(encoding="utf-8"))
    connection = connect_database(":memory:")
    repository = MarketDataRepository(connection)
    return build_full_validation_report(repository, provider_name="mock", report_path=None)


def _build_strategy_diagnosis_report() -> dict:
    report_path = ROOT / "reports" / "strategy_diagnosis_report.json"
    if report_path.exists():
        return json.loads(report_path.read_text(encoding="utf-8"))
    connection = connect_database(":memory:")
    repository = MarketDataRepository(connection)
    return build_strategy_diagnosis_report(repository, provider_name="mock", report_path=None)


def _report_page_css() -> str:
    return """
        :root {
          color-scheme: light;
          --bg: #f6f7f9;
          --panel: #ffffff;
          --text: #1d2433;
          --muted: #5f6b7a;
          --line: #d8dee8;
          --accent: #2563eb;
        }
        * { box-sizing: border-box; }
        body {
          margin: 0;
          background: var(--bg);
          color: var(--text);
          font-family: Arial, "Microsoft YaHei", sans-serif;
        }
        header {
          background: var(--panel);
          border-bottom: 1px solid var(--line);
          padding: 22px 32px 18px;
        }
        main {
          max-width: 1180px;
          margin: 0 auto;
          padding: 26px 24px 40px;
        }
        h1 { margin: 0 0 8px; font-size: 26px; letter-spacing: 0; }
        h2 { margin: 0 0 12px; font-size: 20px; letter-spacing: 0; }
        section { margin-bottom: 24px; }
        p { margin: 0; color: var(--muted); line-height: 1.6; }
        a { color: var(--accent); }
        table {
          width: 100%;
          border-collapse: collapse;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          overflow: hidden;
        }
        th, td {
          padding: 13px 14px;
          border-bottom: 1px solid var(--line);
          text-align: left;
          vertical-align: middle;
          font-size: 14px;
        }
        th { background: #eef2f7; color: #344054; font-weight: 700; }
        tr:last-child td { border-bottom: 0; }
        @media (max-width: 820px) {
          header { padding: 18px 18px 14px; }
          main { padding: 18px 12px 28px; }
          table { display: block; overflow-x: auto; }
          th, td { white-space: nowrap; }
        }
    """


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8025, reload=False)
