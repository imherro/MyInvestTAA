from __future__ import annotations

from html import escape
import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.benchmark import compare_strategies
from backtest.evaluation import rolling_analysis
from backtest.simulator import run_sample_backtest
from backtest.taa import run_taa_backtest
from backtest.research import load_research_backtest_report
from backtest.execution import load_execution_backtest_report, load_mapping_improvement_report, load_proxy_research_report, load_mapping_proposal_report, load_counterfactual_report, load_price_dataset_manifest, load_mapping_attribution_report, load_mapping_review_report, load_mapping_approval_package, load_mapping_decision_ledger, load_mapping_approval_record, load_execution_aware_shadow_portfolio, load_approval_integrity_seal, load_transaction_status
from data_pipeline import (
    build_full_validation_report,
    build_real_performance_report,
    build_strategy_diagnosis_report,
    build_validated_performance_report,
    run_live_backtest_report,
)
from engine.allocation import build_allocation_recommendation
from engine.asset_registry import (
    build_research_universe_readiness,
    build_research_universe_audit,
    load_asset_mappings,
    load_execution_data_availability_report,
    load_execution_universe,
    load_metadata_suggestions_report,
    load_research_data_availability_report,
    load_research_universe,
    load_return_basis_review_report,
)
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
from decision.current_market.explain import decision_headline
from release.orchestrator import load_release_json
from release.web_contracts import primary_navigation_html
from storage import MarketDataRepository, connect_database


UNIFIED_HEADER_SCRIPT_URL = "https://invest.okbbc.com/header.js"
UNIFIED_FOOTER_SCRIPT_URL = "https://invest.okbbc.com/footer.js"


app = FastAPI(
    title="MyInvestTAA",
    description="Tactical Asset Allocation MVP with drawdown and anchor scoring.",
    version="0.1.0",
)


def _unified_shell_scripts() -> str:
    return (
        f'\n    <script src="{UNIFIED_HEADER_SCRIPT_URL}" defer></script>\n'
        f'    <script src="{UNIFIED_FOOTER_SCRIPT_URL}" defer></script>\n'
    )


def _inject_unified_shell(html: str) -> str:
    if UNIFIED_HEADER_SCRIPT_URL in html and UNIFIED_FOOTER_SCRIPT_URL in html:
        return html

    scripts = _unified_shell_scripts()
    if "</head>" in html:
        return html.replace("</head>", f"{scripts}</head>", 1)
    if "</body>" in html:
        return html.replace("</body>", f"{scripts}</body>", 1)
    return f"{html}{scripts}"


def _apply_final_information_architecture(html: str, path: str) -> str:
    if path == "/current-decision":
        html = html.replace("<title>Current Market Decision</title>", "<title>当前配置决策</title>")
        header = (
            '<header><h1>当前配置决策</h1>'
            '<p>本页汇总最近一次经过来源校验的离线决策快照，用于人工判断。它不会生成订单，也不会自动替换 V11。</p>'
            '<p><span class="tag good">已验证快照</span><span class="tag warn">仅供人工审核</span><span class="tag blocked">非交易指令</span></p>'
            f'{_primary_navigation()}</header>'
        )
        html = _replace_html_region(html, "<header>", "</header>", header)
        html = html.replace("<h2>Decision Status</h2>", "<h2>当前结论</h2>")
    elif path == "/v11-current-allocation":
        html = html.replace("<title>V11 Current Allocation</title>", "<title>V11 模型配置</title>")
        header = (
            '<header><h1>V11 模型配置</h1>'
            '<p>这是 V11 正式候选模型的离线配置快照，不是下单指令，也不表示系统已获得自动交易授权。</p>'
            '<p><span class="tag good">正式候选模型</span><span class="tag warn">模型输出</span><span class="tag blocked">未授权自动交易</span></p>'
            f'{_primary_navigation()}</header>'
        )
        html = _replace_html_region(html, "<header>", "</header>", header)
    elif path in {"/research-backtest", "/execution-backtest", "/shadow-portfolio"}:
        label = {
            "/research-backtest": "研究资产层历史验证，不等于真实 ETF 实盘收益。",
            "/execution-backtest": "真实 ETF 执行验证；当前未通过既定覆盖率门槛。",
            "/shadow-portfolio": "实验性 Shadow 配置，不是生产组合，也不能替代 V11。",
        }[path]
        notice = f'<section><p><strong>高级研究/审计页面：</strong>{label} 本页内容均为非交易指令。</p><p><a href="/research-validation">返回研究与执行验证</a></p></section>'
        html = html.replace("<main>", f"<main>{notice}", 1)
    if path in {"/", "/current-decision", "/v11-current-allocation", "/research-validation", "/system-status"}:
        html = html.replace("</style>", f"{_product_css()}</style>", 1)
    return html


def _replace_html_region(html: str, start: str, end: str, replacement: str) -> str:
    start_index = html.find(start)
    end_index = html.find(end, start_index + len(start))
    if start_index < 0 or end_index < 0:
        return html
    return html[:start_index] + replacement + html[end_index + len(end):]


@app.middleware("http")
async def add_unified_shell_to_html(request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        return response

    body = b""
    async for chunk in response.body_iterator:
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        body += chunk

    charset = getattr(response, "charset", None) or "utf-8"
    html = _apply_final_information_architecture(
        body.decode(charset), request.url.path
    )
    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(
        content=_inject_unified_shell(html),
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
        background=response.background,
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


@app.get("/api/research/benchmark-validation")
def get_benchmark_validation() -> dict:
    return _build_strategy_diagnosis_report()["benchmark"]["validation"]


@app.get("/api/research/strategy-registry")
def get_strategy_registry() -> dict:
    return _build_strategy_diagnosis_report()["strategy_registry"]


@app.get("/api/research/selection-analysis")
def get_selection_analysis() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["selection_analysis"]


@app.get("/api/research/walk-forward")
def get_walk_forward() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["walk_forward"]


@app.get("/api/research/promotion")
def get_promotion() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["promotion"]


@app.get("/api/research/adaptive-selection")
def get_adaptive_selection() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["adaptive_selection"]


@app.get("/api/research/exposure-analysis")
def get_exposure_analysis() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["exposure_analysis"]


@app.get("/api/research/strategy-selection")
def get_strategy_selection() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["strategy_selection"]


@app.get("/api/research/robustness")
def get_robustness() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["robustness"]


@app.get("/api/research/final-strategy")
def get_final_strategy() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["final_strategy"]


@app.get("/api/research/stress")
def get_stress() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["stress"]


@app.get("/api/research/production-readiness")
def get_production_readiness() -> dict:
    return _build_strategy_diagnosis_report()["diagnosis"]["production_readiness"]


@app.get("/api/research/universe")
def get_research_universe() -> dict:
    return {
        "research_assets": [asset.as_dict() for asset in load_research_universe()],
        "execution_assets": [asset.as_dict() for asset in load_execution_universe()],
        "mappings": [mapping.as_dict() for mapping in load_asset_mappings()],
    }


@app.get("/api/research/universe-audit")
def get_research_universe_audit() -> dict:
    return {"audit": build_research_universe_audit()}


@app.get("/api/research/universe-data-audit")
def get_research_universe_data_audit(tushare: bool = False) -> dict:
    return load_research_data_availability_report(tushare=tushare)


@app.get("/api/research/universe-metadata-suggestions")
def get_research_universe_metadata_suggestions() -> dict:
    return load_metadata_suggestions_report()


@app.get("/api/research/return-basis-review")
def get_research_return_basis_review() -> dict:
    return load_return_basis_review_report()


@app.get("/api/research/universe-readiness")
def get_research_universe_readiness() -> dict:
    return build_research_universe_readiness()


@app.get("/api/research/research-backtest")
def get_research_backtest_report() -> dict:
    return load_research_backtest_report()


@app.get("/api/research/research-backtest-diagnostics")
def get_research_backtest_diagnostics() -> dict:
    report = load_research_backtest_report()
    if not report.get("available"):
        return report
    return {
        "available": True,
        "diagnostics": report.get("diagnostics", {}),
        "constraint_diagnostics": report.get("constraint_diagnostics", {}),
        "decision": report.get("decision", {}),
    }


@app.get("/api/research/execution-backtest")
def get_execution_backtest_report() -> dict:
    return load_execution_backtest_report()


@app.get("/api/research/execution-universe-data-audit")
def get_execution_universe_data_audit() -> dict:
    return load_execution_data_availability_report()


@app.get("/api/research/execution-mapping-improvement")
def get_execution_mapping_improvement() -> dict:
    return load_mapping_improvement_report()


@app.get("/api/research/execution-proxy-research")
def get_execution_proxy_research() -> dict:
    return load_proxy_research_report()

@app.get("/api/research/execution-mapping-proposal")
def get_execution_mapping_proposal() -> dict:
    return load_mapping_proposal_report()

@app.get("/api/research/execution-mapping-counterfactual")
def get_execution_mapping_counterfactual() -> dict:
    return load_counterfactual_report()

@app.get("/api/research/execution-mapping-attribution")
def get_execution_mapping_attribution() -> dict:
    return load_mapping_attribution_report()

@app.get("/api/research/execution-mapping-review")
def get_execution_mapping_review() -> dict:
    return load_mapping_review_report()

@app.get("/api/research/execution-price-provenance")
def get_execution_price_provenance() -> dict:
    return load_price_dataset_manifest()

@app.get("/api/research/execution-mapping-approval-package/{asset_id}")
def get_execution_mapping_approval_package(asset_id: str) -> dict:
    return load_mapping_approval_package(asset_id)

@app.get("/api/research/execution-mapping-decision-ledger")
def get_execution_mapping_decision_ledger() -> dict:
    return load_mapping_decision_ledger()

@app.get("/api/research/execution-mapping-approval-record")
def get_execution_mapping_approval_record() -> dict:
    return load_mapping_approval_record()

@app.get("/api/research/execution-aware-shadow-portfolio")
def get_execution_aware_shadow_portfolio() -> dict:
    return load_execution_aware_shadow_portfolio()

@app.get("/api/research/execution-mapping-approval-integrity")
def get_execution_mapping_approval_integrity() -> dict:
    return load_approval_integrity_seal()

@app.get("/api/research/execution-mapping-transaction-status")
def get_execution_mapping_transaction_status() -> dict:
    return load_transaction_status()


@app.get("/api/decision/current-market")
def get_current_market_decision() -> dict:
    return load_release_json("current_market_decision.json")


@app.get("/api/decision/v11-current-allocation")
def get_v11_current_allocation() -> dict:
    return load_release_json("v11_current_allocation.json")


@app.get("/api/system/release-manifest")
def get_system_release_manifest() -> dict:
    return load_release_json("release_manifest.json")


@app.get("/api/system/acceptance")
def get_system_acceptance() -> dict:
    return load_release_json("system_acceptance_report.json")


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


def _primary_navigation() -> str:
    return primary_navigation_html()


def _product_css() -> str:
    return """
      :root { color-scheme: light; --bg:#f5f7f8; --panel:#fff; --ink:#17202a; --muted:#5b6874; --line:#d8dee3; --green:#116149; --red:#a32929; --blue:#175ea8; --amber:#8a5a00; }
      * { box-sizing:border-box; }
      body { margin:0; background:var(--bg); color:var(--ink); font-family:Arial,"Microsoft YaHei",sans-serif; line-height:1.6; }
      header, main, footer { width:min(1180px,calc(100% - 32px)); margin:0 auto; }
      header { padding:26px 0 14px; }
      h1 { margin:0; font-size:32px; letter-spacing:0; }
      h2 { font-size:22px; margin:0 0 14px; letter-spacing:0; }
      h3 { font-size:17px; margin:0 0 8px; letter-spacing:0; }
      p { margin:7px 0; }
      .subtle { color:var(--muted); }
      .primary-nav { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:1px; margin:18px 0; border:1px solid var(--line); background:var(--line); }
      .primary-nav a { background:#fff; color:var(--ink); text-decoration:none; padding:12px; font-weight:700; min-width:0; }
      .primary-nav a span { display:block; color:var(--muted); font-size:12px; font-weight:400; }
      .status-strip { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:8px; margin:16px 0; }
      .status-item, section, .card { background:var(--panel); border:1px solid var(--line); border-radius:6px; }
      .status-item { padding:11px; }
      .status-item strong { display:block; font-size:14px; }
      .status-item span { display:block; color:var(--muted); font-size:12px; }
      .status-good { border-left:4px solid var(--green); }
      .status-blocked { border-left:4px solid var(--red); }
      main { display:grid; gap:14px; padding-bottom:30px; min-width:0; }
      section { padding:20px; min-width:0; }
      .hero { border-left:5px solid var(--blue); }
      .alert { border-left:5px solid var(--red); background:#fff8f8; }
      .grid-2 { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
      .grid-3 { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
      .card { padding:16px; min-width:0; overflow-wrap:anywhere; }
      .tag { display:inline-block; border:1px solid var(--line); padding:2px 7px; margin:0 5px 5px 0; font-size:12px; font-weight:700; }
      .tag.good { color:var(--green); border-color:#87b4a5; }
      .tag.warn { color:var(--amber); border-color:#d8bd7a; }
      .tag.blocked { color:var(--red); border-color:#d8a0a0; }
      .actions { display:flex; flex-wrap:wrap; gap:9px; margin-top:16px; }
      .button { display:inline-flex; align-items:center; min-height:42px; padding:8px 14px; border:1px solid var(--blue); color:var(--blue); text-decoration:none; font-weight:700; border-radius:4px; }
      .button.primary { background:var(--blue); color:#fff; }
      ul, ol { margin:8px 0; padding-left:23px; }
      table { width:100%; border-collapse:collapse; }
      th, td { border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }
      .table-wrap { overflow-x:auto; }
      details { border-top:1px solid var(--line); padding-top:10px; margin-top:12px; }
      summary { cursor:pointer; font-weight:700; }
      footer { color:var(--muted); border-top:1px solid var(--line); padding:18px 0 28px; }
      @media (max-width:900px) { .primary-nav { grid-template-columns:repeat(2,minmax(0,1fr)); } .status-strip { grid-template-columns:repeat(3,minmax(0,1fr)); } .grid-3 { grid-template-columns:1fr; } table { max-width:100%; } }
      @media (max-width:560px) { header,main,footer { width:min(100% - 20px,1180px); } h1 { font-size:26px; } .primary-nav,.status-strip,.grid-2 { grid-template-columns:1fr; } section { padding:15px; } }
    """


@app.get("/", response_class=HTMLResponse)
def system_home() -> str:
    manifest = load_release_json("release_manifest.json")
    acceptance = load_release_json("system_acceptance_report.json")
    decision = load_release_json("current_market_decision.json")
    v11 = load_release_json("v11_current_allocation.json")
    release_ok = bool(
        manifest.get("verified") is True
        and acceptance.get("system_acceptance_passed") is True
        and not acceptance.get("blocking_errors")
    )
    decision_ready = decision.get("ready_for_user_review") is True if release_ok else False
    execution = decision.get("execution_validation", {})
    shadow_weights = decision.get("execution_shadow", {}).get("etf_weights", {})
    shadow_cash = float(shadow_weights.get("CASH", 0.0)) if isinstance(shadow_weights, dict) else 0.0
    v11_equity = float(v11.get("equity_weight", 0.0) or 0.0)
    v11_cash = float(v11.get("cash_weight", 0.0) or 0.0)
    blocking = acceptance.get("blocking_errors", [])
    reasons = execution.get("reasons", [])
    main_action = (
        '<a class="button primary" href="/current-decision">查看当前配置决策</a>'
        if decision_ready
        else '<a class="button primary" href="/system-status">查看阻塞原因</a>'
    )
    blocking_html = "".join(f"<li>{escape(str(item))}</li>" for item in (blocking or reasons)) or "<li>无系统级阻塞；执行验证门槛仍未通过。</li>"
    release_label = "已验证" if release_ok else "不可用或未通过"
    release_class = "status-good" if release_ok else "status-blocked"
    decision_label = "可供人工审核" if decision_ready else "当前不可依赖"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>MyInvestTAA 系统首页</title><style>{_product_css()}</style></head><body>
    <header><h1>MyInvestTAA</h1><p class="subtle">离线、多层、可验证的资产配置决策支持系统</p>{_primary_navigation()}</header>
    <main>
      <div class="status-strip" aria-label="系统摘要">
        <div class="status-item {release_class}"><strong>{release_label}</strong><span>系统发布状态</span></div>
        <div class="status-item"><strong>{escape(str(manifest.get('market_data_as_of','不可用')))}</strong><span>市场数据截至</span></div>
        <div class="status-item"><strong>{escape(str(manifest.get('decision_date','不可用')))}</strong><span>决策日期</span></div>
        <div class="status-item"><strong>{decision_label}</strong><span>当前快照</span></div>
        <div class="status-item status-blocked"><strong>未授权</strong><span>自动交易</span></div>
        <div class="status-item status-blocked"><strong>{'已通过' if execution.get('ready') else '尚未通过'}</strong><span>执行验证</span></div>
      </div>
      <section class="{'hero' if decision_ready else 'alert'}"><h2>{'现在该看什么' if decision_ready else '当前结论不可依赖'}</h2><p>{'当前系统已生成一份经过来源校验的本地配置快照。建议先查看“当前配置决策”，了解市场状态、V11、Shadow 以及尚未通过的执行条件。' if decision_ready else '发布或必要来源未通过完整性检查。请先查看系统与数据状态；在修复前不要把页面内容当作当前配置结论。'}</p><div class="actions">{main_action}<a class="button" href="/v11-current-allocation">查看 V11 模型配置</a></div></section>
      <section><h2>普通用户建议阅读顺序</h2><ol><li>先确认上方系统状态没有红色阻塞。</li><li>进入“当前配置决策”，查看可供人工审核的综合快照。</li><li>需要了解正式候选模型时查看“V11 模型配置”。</li><li>只有需要研究细节时进入“研究与执行验证”。</li><li>需要核查数据、版本和来源哈希时进入“系统与数据状态”。</li></ol></section>
      <section><h2>当前市场与配置摘要</h2><div class="grid-3"><div class="card"><h3>市场和风险</h3><p>市场：{escape(str(decision.get('market_state',{}).get('regime','不可用')))}</p><p>风险：{escape(str(decision.get('market_state',{}).get('risk_level','不可用')))}</p></div><div class="card"><h3>V11 模型</h3><p>风险资产：{v11_equity:.1%}</p><p>现金：{v11_cash:.1%}</p></div><div class="card"><h3>Execution Shadow</h3><p>ETF：{1-shadow_cash:.1%}</p><p>现金：{shadow_cash:.1%}</p><p class="subtle">实验性配置，不是生产组合。</p></div></div></section>
      <section><h2>三种结果如何理解</h2><div class="grid-3"><div class="card"><span class="tag good">正式候选模型</span><h3>V11 模型配置</h3><p>当前离线模型权重。它是模型输出，但尚未授权自动交易。</p></div><div class="card"><span class="tag warn">研究结果</span><h3>Research 配置</h3><p>用于验证资产配置逻辑，不代表能买到完全相同的工具。</p></div><div class="card"><span class="tag blocked">实验性 Shadow</span><h3>Execution Shadow</h3><p>把研究权重映射为真实 ETF 和现金后的实验快照，不是生产组合。</p></div></div></section>
      <section><h2>当前限制</h2><ul><li>Execution Validation 尚未通过。</li><li>Shadow 中的 research-only 资产会转为现金，因此当前现金约 40%。</li><li>931743 使用主题接近但覆盖更宽的 medium-quality 半导体 ETF 代理。</li><li>市场和 ETF 数据是离线快照，不是实时行情。</li><li>所有结果只供人工审核。</li></ul><h3>主要阻塞或限制原因</h3><ul>{blocking_html}</ul></section>
      <section><h2>本系统不会做什么</h2><div class="grid-2"><ul><li>不会自动下单或计算买卖数量。</li><li>不会提供目标价格或任何买入、卖出操作按钮。</li><li>不会自动选择 V11 或 Shadow。</li></ul><ul><li>不会合并生成未经验证的新组合。</li><li>不会把研究回测直接当成实盘建议。</li><li>不会因历史收益较高而自动替换 V11。</li></ul></div></section>
      <section><h2>高级入口</h2><div class="actions"><a class="button" href="/research-validation">研究与执行验证</a><a class="button" href="/system-status">系统与数据状态</a></div></section>
    </main><footer>数据截至 {escape(str(manifest.get('market_data_as_of','不可用')))} · Release {escape(str(manifest.get('release_id','不可用')))} · 非交易指令 · <a href="/system-status">查看文档清单</a></footer>{_unified_shell_scripts()}</body></html>"""


@app.get("/legacy-dashboard", response_class=HTMLResponse)
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
        <p>Drawdown + Asset Anchor MVP. 输出为资产配置研究权重信号，不是交易指令。<a href="/current-decision">Current Decision</a> · <a href="/v11-current-allocation">V11 Current Allocation</a> · <a href="/research">Research Report</a> · <a href="/pipeline">Data Pipeline</a> · <a href="/real-research">Real Market Research</a> · <a href="/research-universe">Research Universe</a> · <a href="/research-backtest">Research Backtest</a> · <a href="/execution-backtest">Execution Backtest</a> · <a href="/shadow-portfolio">Shadow Portfolio</a> · <a href="/validation">Validation Report</a> · <a href="/experiment">Experiment Report</a> · <a href="/diagnosis">Strategy Diagnosis</a> · <a href="/benchmark-validation">Benchmark Validation</a> · <a href="/strategy-governance">Strategy Governance</a> · <a href="/selection-research">Selection Research</a> · <a href="/strategy-promotion">Strategy Promotion</a> · <a href="/adaptive-strategy">Adaptive Strategy</a> · <a href="/risk-exposure">Risk Exposure</a> · <a href="/final-strategy">Final Strategy</a> · <a href="/production-readiness">Production Readiness</a></p>
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


@app.get("/research-validation", response_class=HTMLResponse)
def research_validation_page() -> str:
    decision = load_release_json("current_market_decision.json")
    execution = decision.get("execution_validation", {})
    reasons = "".join(f"<li>{escape(str(value))}</li>" for value in execution.get("reasons", [])) or "<li>未记录原因，请查看系统状态。</li>"
    cards = (
        ("Research Backtest", "/research-backtest", "研究资产层的历史配置测试，用于判断配置逻辑，不等于真实 ETF 收益。", "研究结果"),
        ("Execution Backtest", "/execution-backtest", "使用真实 ETF 数据验证研究配置能否执行，以及执行后损失多少收益或增加多少风险。", "执行验证"),
        ("Execution-Aware Shadow", "/shadow-portfolio", "将最新研究权重转换为真实 ETF 和现金的实验性配置，不是生产组合。", "实验性 Shadow"),
        ("Mapping Evidence", "/system-status#mapping-governance", "记录研究指数与 ETF 代理关系、人工批准和语义限制，主要供审计使用。", "高级审计内容"),
    )
    card_html = "".join(f'<div class="card"><span class="tag warn">{tag}</span><h3>{title}</h3><p>{description}</p><a class="button" href="{href}">查看详情</a></div>' for title, href, description, tag in cards)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>研究与执行验证</title><style>{_product_css()}</style></head><body><header><h1>研究与执行验证</h1><p class="subtle">供高级用户查看研究策略、真实 ETF 执行映射、执行差距和 Shadow 证据。所有内容均不用于直接交易。</p>{_primary_navigation()}</header><main><section class="alert"><span class="tag blocked">尚未通过验证</span><h2>Execution Validation 当前未通过</h2><p>这不代表整个系统不可用；它表示研究配置映射到真实 ETF 后，历史覆盖率和不可执行月份尚未达到既定门槛。</p><ul>{reasons}</ul></section><section><h2>四类高级内容</h2><div class="grid-2">{card_html}</div></section><section><h2>如何正确理解</h2><ul><li>Research 验证配置逻辑，不等于 ETF 实盘收益。</li><li>Execution 验证真实 ETF 能否复现研究结果。</li><li>Shadow 是实验快照，不能替代 V11，也不能直接下单。</li><li>medium-quality mapping 表示主题接近但范围更宽，并非直接跟踪。</li></ul></section></main><footer>高级研究内容 · 非交易指令</footer>{_unified_shell_scripts()}</body></html>"""


@app.get("/system-status", response_class=HTMLResponse)
def system_status_page() -> str:
    manifest = load_release_json("release_manifest.json")
    acceptance = load_release_json("system_acceptance_report.json")
    available = manifest.get("verified") is True and acceptance.get("system_acceptance_passed") is True
    conditions = "".join(f"<li>{escape(str(value))}</li>" for value in acceptance.get("known_nonblocking_conditions", [])) or "<li>无可用验收报告。</li>"
    errors = "".join(f"<li>{escape(str(value))}</li>" for value in acceptance.get("blocking_errors", [])) or "<li>无阻塞错误。</li>"
    protected = acceptance.get("protected_files", {})
    sections = (
        ("Data Integrity", acceptance.get("data_integrity", {}).get("verified")),
        ("V11 Integrity", acceptance.get("v11_snapshot_integrity", {}).get("verified")),
        ("Execution Validation", acceptance.get("execution_integrity", {}).get("execution_validation_ready")),
        ("Mapping Governance", acceptance.get("mapping_governance_integrity", {}).get("verified")),
        ("Shadow Integrity", acceptance.get("shadow_integrity", {}).get("verified")),
        ("Current Decision Status", acceptance.get("current_decision_integrity", {}).get("verified")),
        ("Reproducibility", acceptance.get("reproducibility", {}).get("verified")),
        ("Protected Files", protected.get("verified")),
    )
    status_html = "".join(f'<div class="card"><h3>{name}</h3><span class="tag {"good" if value else "blocked"}">{"已验证" if value else "尚未通过验证"}</span></div>' for name, value in sections)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>系统与数据状态</title><style>{_product_css()}</style></head><body><header><h1>系统与数据状态</h1><p><strong>This system status page verifies a reproducible local decision-support release. It does not authorize automated trading.</strong></p>{_primary_navigation()}</header><main><section class="{'hero' if available else 'alert'}"><h2>{'系统验收已通过' if available else '系统验收不可用或未通过'}</h2><div class="grid-3"><div class="card"><h3>Release ID</h3><p>{escape(str(manifest.get('release_id','不可用')))}</p></div><div class="card"><h3>Build Mode</h3><p>{escape(str(manifest.get('build_mode','不可用')))}</p></div><div class="card"><h3>Commit SHA</h3><p>{escape(str(manifest.get('commit_sha','不可用')))}</p></div><div class="card"><h3>Market Data As-Of</h3><p>{escape(str(manifest.get('market_data_as_of','不可用')))}</p></div><div class="card"><h3>Decision Date</h3><p>{escape(str(manifest.get('decision_date','不可用')))}</p></div><div class="card"><h3>Production Boundary</h3><p>未授权自动交易</p></div></div></section><section><h2>验收项目</h2><div class="grid-3">{status_html}</div></section><section id="mapping-governance"><h2>已知非阻塞条件</h2><ul>{conditions}</ul></section><section><h2>阻塞错误</h2><ul>{errors}</ul></section><section><h2>文档入口</h2><div class="table-wrap"><table><thead><tr><th>文档</th><th>用途</th></tr></thead><tbody><tr><td>README.md</td><td>普通用户快速开始</td></tr><tr><td>docs/OFFLINE_BUILD.md</td><td>离线重建和验证</td></tr><tr><td>docs/OPERATIONS.md</td><td>恢复、清理和故障处理</td></tr><tr><td>docs/DATA_CONTRACTS.md</td><td>报告和字段契约</td></tr><tr><td>docs/LIMITATIONS.md</td><td>当前限制和非交易边界</td></tr></tbody></table></div><details><summary>技术审计信息</summary><p>Release manifest、acceptance report、来源哈希和受保护文件状态可通过只读 API 查看。</p><ul><li><a href="/api/system/release-manifest">Release Manifest API</a></li><li><a href="/api/system/acceptance">System Acceptance API</a></li><li><a href="/diagnosis">Strategy Diagnosis（高级审计）</a></li><li><a href="/production-readiness">Production Readiness（高级审计）</a></li></ul></details></section></main><footer>系统验收与数据审计入口 · 非交易指令</footer>{_unified_shell_scripts()}</body></html>"""


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
        <p>诊断当前 TAA 策略弱点并比较 V1/V2/V3/V4/V5/V6/V7/V8/V9/V10。<a href="/experiment">Experiment Report</a> · <a href="/strategy-governance">Strategy Governance</a> · <a href="/selection-research">Selection Research</a> · <a href="/strategy-promotion">Strategy Promotion</a> · <a href="/adaptive-strategy">Adaptive Strategy</a> · <a href="/risk-exposure">Risk Exposure</a> · <a href="/final-strategy">Final Strategy</a></p>
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


@app.get("/benchmark-validation", response_class=HTMLResponse)
def benchmark_validation_page() -> str:
    report = _build_strategy_diagnosis_report()["benchmark"]["validation"]
    rows = "\n".join(_benchmark_validation_rows(report["rows"]))
    issues = "; ".join(report["issues"]) if report["issues"] else "No benchmark sanity issue detected"

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Benchmark Validation</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Benchmark Validation</h1>
        <p>Benchmark sanity check，收益和回撤单位均为百分比。<a href="/diagnosis">Strategy Diagnosis</a></p>
      </header>
      <main>
        <section>
          <h2>Summary</h2>
          <table>
            <tbody>
              <tr><td>Weight Check</td><td>{report["weight_check"]}</td></tr>
              <tr><td>Return Check</td><td>{report["return_check"]}</td></tr>
              <tr><td>Unit</td><td>{report["unit"]}</td></tr>
              <tr><td>Issues</td><td>{escape(issues)}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Rows</h2>
          <table>
            <thead>
              <tr>
                <th>策略</th>
                <th>权重检查</th>
                <th>收益检查</th>
                <th>权重合计</th>
                <th>年化收益</th>
                <th>最大回撤</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/strategy-governance", response_class=HTMLResponse)
def strategy_governance_page() -> str:
    registry = _build_strategy_diagnosis_report()["strategy_registry"]
    rows = "\n".join(_strategy_registry_rows(registry["rows"]))
    production_candidate = registry.get("production_candidate") or "None"

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Strategy Governance</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Strategy Governance</h1>
        <p>管理当前生产候选版本、测试版本和归档版本。<a href="/diagnosis">Strategy Diagnosis</a></p>
      </header>
      <main>
        <section>
          <h2>Production Candidate</h2>
          <table>
            <tbody>
              <tr><td>Version</td><td>{escape(str(production_candidate))}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Registry</h2>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>状态</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>Calmar</th>
                <th>Promotion</th>
                <th>验证窗口</th>
                <th>审批</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/selection-research", response_class=HTMLResponse)
def selection_research_page() -> str:
    report = _build_strategy_diagnosis_report()["diagnosis"]["selection_analysis"]
    rows = "\n".join(_selection_analysis_rows(report["rows"]))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Selection Research</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Selection Research</h1>
        <p>展示 V8 自适应权重、主题动量、股票级宽度和相对强度选择证据。<a href="/diagnosis">Strategy Diagnosis</a></p>
      </header>
      <main>
        <section>
          <h2>Latest Selection</h2>
          <table>
            <thead>
              <tr>
                <th>资产</th>
                <th>主题</th>
                <th>机会分</th>
                <th>相对强度</th>
                <th>主题动量</th>
                <th>宽度</th>
                <th>股票宽度</th>
                <th>趋势</th>
                <th>理由</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/strategy-promotion", response_class=HTMLResponse)
def strategy_promotion_page() -> str:
    report = _build_strategy_diagnosis_report()["diagnosis"]
    promotion = report["promotion"]
    walk_forward = report["walk_forward"]
    promotion_rows = "\n".join(_promotion_rows(promotion["rows"]))
    walk_rows = "\n".join(_walk_forward_rows(walk_forward.get("versions", {}).values()))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Strategy Promotion</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Strategy Promotion</h1>
        <p>展示 Walk Forward 稳定性和自动晋升规则。<a href="/strategy-governance">Strategy Governance</a></p>
      </header>
      <main>
        <section>
          <h2>Promotion</h2>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>晋升</th>
                <th>Promotion Score</th>
                <th>验证窗口</th>
                <th>胜率</th>
                <th>平均 Alpha</th>
                <th>状态</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>{promotion_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Walk Forward</h2>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>窗口</th>
                <th>胜率</th>
                <th>平均 Alpha</th>
                <th>最差 Alpha</th>
                <th>回撤通过率</th>
                <th>稳定</th>
              </tr>
            </thead>
            <tbody>{walk_rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/adaptive-strategy", response_class=HTMLResponse)
def adaptive_strategy_page() -> str:
    report = _build_strategy_diagnosis_report()["diagnosis"]["adaptive_selection"]
    rows = "\n".join(_adaptive_selection_rows(report.get("rows", [])))
    weights = report.get("factor_weights", {}).get("weights", {})
    weight_rows = "\n".join(_adaptive_weight_rows(weights))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Adaptive Strategy</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Adaptive Strategy</h1>
        <p>展示当前 Market Regime 与 V10 动态 Selection 权重。<a href="/diagnosis">Strategy Diagnosis</a> · <a href="/risk-exposure">Risk Exposure</a> · <a href="/final-strategy">Final Strategy</a> · <a href="/production-readiness">Production Readiness</a></p>
      </header>
      <main>
        <section>
          <h2>Current Regime</h2>
          <table>
            <tbody>
              <tr><td>Market Regime</td><td>{escape(str(report.get("regime", "neutral")))}</td></tr>
              <tr><td>Reason</td><td>{escape(str(report.get("factor_weights", {}).get("reason", "")))}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Selection Weights</h2>
          <table>
            <thead>
              <tr><th>因子</th><th>权重</th></tr>
            </thead>
            <tbody>{weight_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Adaptive Selection</h2>
          <table>
            <thead>
              <tr>
                <th>资产</th>
                <th>主题</th>
                <th>机会分</th>
                <th>Regime</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/risk-exposure", response_class=HTMLResponse)
def risk_exposure_page() -> str:
    diagnosis = _build_strategy_diagnosis_report()["diagnosis"]
    exposure = diagnosis["exposure_analysis"]
    selection = diagnosis["strategy_selection"]
    current = exposure.get("current", {})
    reason = ", ".join(current.get("reason", []))
    exposure_rows = "\n".join(_exposure_history_rows(exposure.get("rows", [])))
    selection_rows = "\n".join(_strategy_selection_rows(selection.get("rows", [])))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Risk Exposure</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Risk Exposure</h1>
        <p>展示 V11 风险敞口优化、波动率目标、组合回撤控制和生产策略评分。<a href="/diagnosis">Strategy Diagnosis</a> · <a href="/strategy-promotion">Strategy Promotion</a> · <a href="/final-strategy">Final Strategy</a> · <a href="/production-readiness">Production Readiness</a></p>
      </header>
      <main>
        <section>
          <h2>Current Exposure</h2>
          <table>
            <tbody>
              <tr><td>Date</td><td>{escape(str(exposure.get("date", "-")))}</td></tr>
              <tr><td>Regime</td><td>{escape(str(current.get("regime", "-")))}</td></tr>
              <tr><td>Target Equity</td><td>{float(current.get("equity_target", 0.0)):.2f}%</td></tr>
              <tr><td>Volatility</td><td>{float(current.get("volatility", 0.0)):.2f}%</td></tr>
              <tr><td>Portfolio Drawdown</td><td>{float(current.get("drawdown", 0.0)):.2f}%</td></tr>
              <tr><td>Breadth</td><td>{_format_optional_percent(current.get("breadth"))}</td></tr>
              <tr><td>Confidence</td><td>{float(current.get("confidence", 0.0)) * 100:.1f}%</td></tr>
              <tr><td>Reason</td><td>{escape(reason)}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Strategy Selection</h2>
          <table>
            <tbody>
              <tr><td>Winner</td><td>{escape(str(selection.get("winner", "-")))}</td></tr>
              <tr><td>Confidence</td><td>{float(selection.get("confidence", 0.0)) * 100:.1f}%</td></tr>
              <tr><td>Production Benchmark</td><td>{escape(str(selection.get("production_version", "-")))}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Production Score</h2>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>生产评分</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>Calmar</th>
                <th>Walk Forward</th>
                <th>Worst Window</th>
                <th>Stability</th>
              </tr>
            </thead>
            <tbody>{selection_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Exposure History</h2>
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>Regime</th>
                <th>目标权益</th>
                <th>波动率</th>
                <th>回撤</th>
                <th>宽度</th>
                <th>置信度</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>{exposure_rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/final-strategy", response_class=HTMLResponse)
def final_strategy_page() -> str:
    diagnosis = _build_strategy_diagnosis_report()["diagnosis"]
    final_strategy = diagnosis["final_strategy"]
    robustness = diagnosis["robustness"]
    candidate = final_strategy.get("production_candidate") or final_strategy.get("candidate") or "None"
    reason = "; ".join(final_strategy.get("reason", []))
    final_rows = "\n".join(_final_strategy_rows(final_strategy.get("rows", [])))
    robustness_rows = "\n".join(_robustness_score_rows(robustness.get("version_scores", [])))
    sensitivity_rows = "\n".join(_parameter_sensitivity_rows(robustness.get("parameter_sensitivity", {}).get("rows", [])))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Final Strategy</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Final Strategy</h1>
        <p>展示 Production Score V2、稳健性分析和最终生产候选。<a href="/diagnosis">Strategy Diagnosis</a> · <a href="/risk-exposure">Risk Exposure</a> · <a href="/production-readiness">Production Readiness</a></p>
      </header>
      <main>
        <section>
          <h2>Production Candidate</h2>
          <table>
            <tbody>
              <tr><td>Candidate</td><td>{escape(str(candidate))}</td></tr>
              <tr><td>Confidence</td><td>{float(final_strategy.get("confidence", 0.0)) * 100:.1f}%</td></tr>
              <tr><td>Production Benchmark</td><td>{escape(str(final_strategy.get("production_version", "-")))}</td></tr>
              <tr><td>Reason</td><td>{escape(reason)}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Production Score V2</h2>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>评分</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>Walk Forward</th>
                <th>Worst Window</th>
                <th>Robustness</th>
                <th>通过</th>
              </tr>
            </thead>
            <tbody>{final_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Robustness</h2>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>稳健分</th>
                <th>Bootstrap中位收益</th>
                <th>Worst 5%</th>
                <th>Best 5%</th>
                <th>中位回撤</th>
                <th>通过</th>
              </tr>
            </thead>
            <tbody>{robustness_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>V10 Parameter Sensitivity</h2>
          <table>
            <thead>
              <tr>
                <th>Target Vol</th>
                <th>DD阈值</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>稳定分</th>
                <th>稳定</th>
              </tr>
            </thead>
            <tbody>{sensitivity_rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/production-readiness", response_class=HTMLResponse)
def production_readiness_page() -> str:
    diagnosis = _build_strategy_diagnosis_report()["diagnosis"]
    readiness = diagnosis["production_readiness"]
    stress = diagnosis["stress"]
    candidate = readiness.get("candidate") or "None"
    status = readiness.get("status", "not_ready")
    reason = "; ".join(readiness.get("reason", []))
    readiness_rows = "\n".join(_production_readiness_rows(readiness.get("rows", [])))
    stress_rows = "\n".join(_stress_rows(stress.get("rows", [])))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Production Readiness</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Production Readiness</h1>
        <p>展示 Production Governance V3、V11 融合策略和压力测试准入状态。<a href="/diagnosis">Strategy Diagnosis</a> · <a href="/final-strategy">Final Strategy</a> · <a href="/risk-exposure">Risk Exposure</a></p>
      </header>
      <main>
        <section>
          <h2>Current Candidate</h2>
          <table>
            <tbody>
              <tr><td>Candidate</td><td>{escape(str(candidate))}</td></tr>
              <tr><td>Status</td><td>{escape(str(status))}</td></tr>
              <tr><td>Confidence</td><td>{float(readiness.get("confidence", 0.0)) * 100:.1f}%</td></tr>
              <tr><td>Reason</td><td>{escape(reason)}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Production Governance V3</h2>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>评分</th>
                <th>状态</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Sharpe</th>
                <th>Walk Forward</th>
                <th>Stress</th>
                <th>Robustness</th>
              </tr>
            </thead>
            <tbody>{readiness_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Stress Validation</h2>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>场景</th>
                <th>年化收益</th>
                <th>最大回撤</th>
                <th>Recovery</th>
                <th>观测</th>
                <th>通过</th>
              </tr>
            </thead>
            <tbody>{stress_rows}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """


@app.get("/research-universe", response_class=HTMLResponse)
def research_universe_page() -> str:
    research_assets = load_research_universe()
    execution_assets = load_execution_universe()
    mappings = load_asset_mappings()
    audit = build_research_universe_audit()
    research_rows = "\n".join(_research_universe_rows([asset.as_dict() for asset in research_assets]))
    execution_rows = "\n".join(_execution_universe_rows([asset.as_dict() for asset in execution_assets]))
    mapping_rows = "\n".join(_asset_mapping_rows([mapping.as_dict() for mapping in mappings]))
    return_basis_rows = "\n".join(_count_rows(audit["return_basis_counts"]))
    data_api_rows = "\n".join(_count_rows(audit["data_api_counts"]))
    mapping_quality_rows = "\n".join(_count_rows(audit["mapping_quality_counts"]))
    warning_rows = "\n".join(_message_rows(audit["warnings"], empty="No universe warnings"))
    error_rows = "\n".join(_message_rows(audit["errors"], empty="No universe errors"))
    data_audit = load_research_data_availability_report()
    data_audit_summary_rows = "\n".join(_data_availability_summary_rows(data_audit))
    data_audit_api_rows = "\n".join(_data_availability_api_rows(data_audit))
    unavailable_asset_rows = "\n".join(_unavailable_data_asset_rows(data_audit))
    data_audit_warning_rows = "\n".join(_data_audit_warning_rows(data_audit))
    tushare_audit = load_research_data_availability_report(tushare=True)
    tushare_audit_summary_rows = "\n".join(_data_availability_summary_rows(tushare_audit))
    tushare_unavailable_rows = "\n".join(_unavailable_data_asset_rows(tushare_audit))
    metadata_suggestions = load_metadata_suggestions_report()
    metadata_suggestion_rows = "\n".join(_metadata_suggestion_rows(metadata_suggestions))
    blocked_metadata_rows = "\n".join(_blocked_metadata_rows(metadata_suggestions))
    return_basis_review = load_return_basis_review_report()
    return_basis_summary_rows = "\n".join(_return_basis_summary_rows(return_basis_review))
    return_basis_manual_rows = "\n".join(_review_asset_rows(return_basis_review, "needs_manual_review"))
    provider_metadata_mismatch_rows = "\n".join(_review_asset_rows(return_basis_review, "provider_metadata_mismatch"))
    unavailable_total_return_rows = "\n".join(_review_asset_rows(return_basis_review, "unavailable_total_return"))
    price_index_monitor_rows = "\n".join(_review_asset_rows(return_basis_review, "price_index_monitor_assets"))
    readiness = build_research_universe_readiness()
    readiness_summary_rows = "\n".join(_readiness_summary_rows(readiness))
    readiness_check_rows = "\n".join(_readiness_check_rows(readiness))
    readiness_blocked_rows = "\n".join(_readiness_blocked_rows(readiness))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Research Universe</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Research Universe</h1>
        <p>研究资产层与 ETF 执行代理层的静态注册表审计。<a href="/">Dashboard</a> · <a href="/real-research">Real Market Research</a> · <a href="/research-backtest">Research Backtest</a> · <a href="/execution-backtest">Execution Backtest</a> · <a href="/production-readiness">Production Readiness</a></p>
      </header>
      <main>
        <section>
          <h2>Universe Audit</h2>
          <table>
            <tbody>
              <tr><td>Research Assets</td><td>{int(audit["research_asset_count"])}</td></tr>
              <tr><td>Execution Assets</td><td>{int(audit["execution_asset_count"])}</td></tr>
              <tr><td>Mappings</td><td>{int(audit["mapping_count"])}</td></tr>
              <tr><td>Eligible For Allocation</td><td>{int(audit["eligible_for_allocation_count"])}</td></tr>
              <tr><td>Industry Monitor</td><td>{int(audit["industry_monitor_count"])}</td></tr>
              <tr><td>Warnings</td><td>{len(audit["warnings"])}</td></tr>
              <tr><td>Errors</td><td>{len(audit["errors"])}</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Return Basis Counts</h2>
          <table>
            <thead><tr><th>Return Basis</th><th>Count</th></tr></thead>
            <tbody>{return_basis_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Data API Counts</h2>
          <table>
            <thead><tr><th>Data API</th><th>Count</th></tr></thead>
            <tbody>{data_api_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Mapping Quality</h2>
          <table>
            <thead><tr><th>Quality</th><th>Count</th></tr></thead>
            <tbody>{mapping_quality_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Data Availability Audit</h2>
          <table>
            <tbody>{data_audit_summary_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Data API Availability</h2>
          <table>
            <thead><tr><th>Data API</th><th>Available</th><th>Unavailable</th></tr></thead>
            <tbody>{data_audit_api_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Unavailable Assets</h2>
          <table>
            <thead><tr><th>Asset</th><th>Data API</th><th>Error</th></tr></thead>
            <tbody>{unavailable_asset_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Data Audit Warnings</h2>
          <table><tbody>{data_audit_warning_rows}</tbody></table>
        </section>
        <section>
          <h2>Real Tushare Audit</h2>
          <table>
            <tbody>{tushare_audit_summary_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Unavailable Tushare Assets</h2>
          <table>
            <thead><tr><th>Asset</th><th>Data API</th><th>Error</th></tr></thead>
            <tbody>{tushare_unavailable_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Metadata Suggestions</h2>
          <table>
            <thead><tr><th>Asset</th><th>Data Start</th><th>Investable Start</th><th>Confidence</th></tr></thead>
            <tbody>{metadata_suggestion_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Blocked Metadata Assets</h2>
          <table>
            <thead><tr><th>Asset</th><th>Reason</th></tr></thead>
            <tbody>{blocked_metadata_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Return Basis Review</h2>
          <table><tbody>{return_basis_summary_rows}</tbody></table>
        </section>
        <section>
          <h2>Research Universe Readiness</h2>
          <table><tbody>{readiness_summary_rows}</tbody></table>
        </section>
        <section>
          <h2>Readiness Checks</h2>
          <table>
            <thead><tr><th>Check</th><th>Status</th></tr></thead>
            <tbody>{readiness_check_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Readiness Blocked Assets</h2>
          <table>
            <thead><tr><th>Asset</th><th>Reason</th></tr></thead>
            <tbody>{readiness_blocked_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Manual Return Basis Review</h2>
          <table>
            <thead><tr><th>Asset</th><th>Return Basis</th><th>Status</th><th>Reason</th></tr></thead>
            <tbody>{return_basis_manual_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Provider Metadata Mismatch</h2>
          <table>
            <thead><tr><th>Asset</th><th>Return Basis</th><th>Status</th><th>Reason</th></tr></thead>
            <tbody>{provider_metadata_mismatch_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Unavailable Total Return Assets</h2>
          <table>
            <thead><tr><th>Asset</th><th>Return Basis</th><th>Status</th><th>Reason</th></tr></thead>
            <tbody>{unavailable_total_return_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Price Index Monitor Assets</h2>
          <table>
            <thead><tr><th>Asset</th><th>Return Basis</th><th>Status</th><th>Reason</th></tr></thead>
            <tbody>{price_index_monitor_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Research Assets</h2>
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>Role</th>
                <th>Category</th>
                <th>Sleeve</th>
                <th>Data API</th>
                <th>Return Basis</th>
                <th>Allocation</th>
              </tr>
            </thead>
            <tbody>{research_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Execution Assets</h2>
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>Data API</th>
                <th>Return Basis</th>
                <th>Investable Start</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>{execution_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Asset Mapping</h2>
          <table>
            <thead>
              <tr>
                <th>Research Asset</th>
                <th>Primary Proxy</th>
                <th>Execution Proxies</th>
                <th>Quality</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>{mapping_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Warnings</h2>
          <table><tbody>{warning_rows}</tbody></table>
        </section>
        <section>
          <h2>Errors</h2>
          <table><tbody>{error_rows}</tbody></table>
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


def _benchmark_validation_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{item["strategy"]}</td>
              <td>{item["weight_check"]}</td>
              <td>{item["return_check"]}</td>
              <td>{item["weight_sum"]:.2f}%</td>
              <td>{item["annual_return"]:.2f}%</td>
              <td>{item["max_drawdown"]:.2f}%</td>
            </tr>
            """
        )
    return html_rows


def _strategy_registry_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        metrics = item.get("metrics", {})
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item["version"]))}</td>
              <td>{escape(str(item["status"]))}</td>
              <td>{float(metrics.get("annual_return", 0.0)):.2f}%</td>
              <td>{float(metrics.get("max_drawdown", 0.0)):.2f}%</td>
              <td>{float(metrics.get("sharpe", 0.0)):.2f}</td>
              <td>{float(metrics.get("calmar", 0.0)):.2f}</td>
              <td>{float(item.get("promotion_score", 0.0)):.2f}</td>
              <td>{int(item.get("validation_windows", 0) or 0)}</td>
              <td>{escape(str(item.get("approval_status", "-")))}</td>
            </tr>
            """
        )
    return html_rows


def _selection_analysis_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        reasons = ", ".join(item.get("selection_reason", []))
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item["name"]))}<span>{escape(str(item["asset"]))}</span></td>
              <td>{escape(str(item["theme"]))}</td>
              <td>{float(item.get("opportunity_score", 0.0)):.2f}</td>
              <td>{float(item.get("relative_strength_score", 0.0)):.2f}</td>
              <td>{float(item.get("theme_momentum_score", 0.0)):.2f}</td>
              <td>{float(item.get("breadth_score", 0.0)):.2f}</td>
              <td>{float(item.get("stock_breadth_score", 0.0)):.2f}</td>
              <td>{float(item.get("trend_score", 0.0)):.2f}</td>
              <td>{escape(reasons)}</td>
            </tr>
            """
        )
    return html_rows


def _promotion_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        reasons = ", ".join(item.get("reasons", []))
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item["version"]))}</td>
              <td>{escape(str(item["promotion"]))}</td>
              <td>{float(item.get("promotion_score", 0.0)):.2f}</td>
              <td>{int(item.get("validation_windows", 0) or 0)}</td>
              <td>{float(item.get("win_rate", 0.0)) * 100:.1f}%</td>
              <td>{float(item.get("avg_alpha", 0.0)):.2f}%</td>
              <td>{escape(str(item.get("approval_status", "-")))}</td>
              <td>{escape(reasons)}</td>
            </tr>
            """
        )
    return html_rows


def _walk_forward_rows(rows) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item["version"]))}</td>
              <td>{int(item.get("windows", 0))}</td>
              <td>{float(item.get("win_rate", 0.0)) * 100:.1f}%</td>
              <td>{float(item.get("avg_alpha", 0.0)):.2f}%</td>
              <td>{float(item.get("min_alpha", 0.0)):.2f}%</td>
              <td>{float(item.get("drawdown_pass_rate", 0.0)) * 100:.1f}%</td>
              <td>{escape(str(item.get("stable", False)))}</td>
            </tr>
            """
        )
    return html_rows


def _adaptive_weight_rows(weights: dict) -> list[str]:
    html_rows: list[str] = []
    for factor, weight in weights.items():
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(factor))}</td>
              <td>{float(weight) * 100:.1f}%</td>
            </tr>
            """
        )
    return html_rows


def _adaptive_selection_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("name", "")))}<span>{escape(str(item.get("asset", "")))}</span></td>
              <td>{escape(str(item.get("theme", "")))}</td>
              <td>{float(item.get("opportunity_score", 0.0)):.2f}</td>
              <td>{escape(str(item.get("adaptive_regime", "")))}</td>
              <td>{escape(str(item.get("adaptive_reason", "")))}</td>
            </tr>
            """
        )
    return html_rows


def _exposure_history_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["<tr><td colspan=\"8\">No exposure decision recorded</td></tr>"]
    html_rows: list[str] = []
    for item in rows:
        reasons = ", ".join(item.get("reason", []))
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("date", "")))}</td>
              <td>{escape(str(item.get("regime", "")))}</td>
              <td>{float(item.get("equity_target", 0.0)):.2f}%</td>
              <td>{float(item.get("volatility", 0.0)):.2f}%</td>
              <td>{float(item.get("drawdown", 0.0)):.2f}%</td>
              <td>{_format_optional_percent(item.get("breadth"))}</td>
              <td>{float(item.get("confidence", 0.0)) * 100:.1f}%</td>
              <td>{escape(reasons)}</td>
            </tr>
            """
        )
    return html_rows


def _strategy_selection_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["<tr><td colspan=\"9\">No strategy selection score recorded</td></tr>"]
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("version", "")))}</td>
              <td>{float(item.get("production_score", 0.0)):.2f}</td>
              <td>{float(item.get("annual_return", 0.0)):.2f}%</td>
              <td>{float(item.get("max_drawdown", 0.0)):.2f}%</td>
              <td>{float(item.get("sharpe", 0.0)):.2f}</td>
              <td>{float(item.get("calmar", 0.0)):.2f}</td>
              <td>{float(item.get("walk_forward_win_rate", 0.0)) * 100:.1f}%</td>
              <td>{float(item.get("walk_forward_min_alpha", 0.0)):.2f}%</td>
              <td>{float(item.get("stability_score", 0.0)):.2f}</td>
            </tr>
            """
        )
    return html_rows


def _final_strategy_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["<tr><td colspan=\"9\">No final strategy score recorded</td></tr>"]
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("version", "")))}</td>
              <td>{float(item.get("production_score_v2", 0.0)):.2f}</td>
              <td>{float(item.get("annual_return", 0.0)):.2f}%</td>
              <td>{float(item.get("max_drawdown", 0.0)):.2f}%</td>
              <td>{float(item.get("sharpe", 0.0)):.2f}</td>
              <td>{float(item.get("walk_forward_win_rate", 0.0)) * 100:.1f}%</td>
              <td>{float(item.get("walk_forward_min_alpha", 0.0)):.2f}%</td>
              <td>{float(item.get("robustness_score", 0.0)):.2f}</td>
              <td>{escape(str(item.get("final_rule_pass", False)))}</td>
            </tr>
            """
        )
    return html_rows


def _robustness_score_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["<tr><td colspan=\"7\">No robustness score recorded</td></tr>"]
    html_rows: list[str] = []
    for item in rows:
        bootstrap = item.get("bootstrap", {})
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("version", "")))}</td>
              <td>{float(item.get("robustness_score", 0.0)):.2f}</td>
              <td>{float(bootstrap.get("median_return", 0.0)):.2f}%</td>
              <td>{float(bootstrap.get("worst_5_percent", 0.0)):.2f}%</td>
              <td>{float(bootstrap.get("best_5_percent", 0.0)):.2f}%</td>
              <td>{float(bootstrap.get("median_max_drawdown", 0.0)):.2f}%</td>
              <td>{escape(str(item.get("pass", False)))}</td>
            </tr>
            """
        )
    return html_rows


def _production_readiness_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["<tr><td colspan=\"9\">No production readiness rows recorded</td></tr>"]
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("version", "")))}</td>
              <td>{float(item.get("production_score_v3", 0.0)):.2f}</td>
              <td>{escape(str(item.get("ready", False)))}</td>
              <td>{float(item.get("annual_return", 0.0)):.2f}%</td>
              <td>{float(item.get("max_drawdown", 0.0)):.2f}%</td>
              <td>{float(item.get("sharpe", 0.0)):.2f}</td>
              <td>{float(item.get("walk_forward_win_rate", 0.0)) * 100:.1f}%</td>
              <td>{float(item.get("stress_score", 0.0)):.2f}</td>
              <td>{float(item.get("robustness_score", 0.0)):.2f}</td>
            </tr>
            """
        )
    return html_rows


def _stress_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["<tr><td colspan=\"7\">No stress rows recorded</td></tr>"]
    html_rows: list[str] = []
    for item in rows:
        recovery = item.get("recovery_time")
        recovery_text = "-" if recovery is None else str(recovery)
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("version", "")))}</td>
              <td>{escape(str(item.get("label", item.get("scenario", ""))))}</td>
              <td>{float(item.get("annual_return", 0.0)):.2f}%</td>
              <td>{float(item.get("max_drawdown", 0.0)):.2f}%</td>
              <td>{escape(recovery_text)}</td>
              <td>{int(item.get("observations", 0) or 0)}</td>
              <td>{escape(str(item.get("pass", False)))}</td>
            </tr>
            """
        )
    return html_rows


def _parameter_sensitivity_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["<tr><td colspan=\"7\">No parameter sensitivity recorded</td></tr>"]
    html_rows: list[str] = []
    for item in rows:
        html_rows.append(
            f"""
            <tr>
              <td>{float(item.get("target_volatility", 0.0)):.1f}%</td>
              <td>{float(item.get("drawdown_threshold", 0.0)):.1f}%</td>
              <td>{float(item.get("annual_return", 0.0)):.2f}%</td>
              <td>{float(item.get("max_drawdown", 0.0)):.2f}%</td>
              <td>{float(item.get("sharpe", 0.0)):.2f}</td>
              <td>{float(item.get("stability_score", 0.0)):.2f}</td>
              <td>{escape(str(item.get("stable", False)))}</td>
            </tr>
            """
        )
    return html_rows


@app.get("/research-backtest", response_class=HTMLResponse)
def research_backtest_page() -> str:
    report = load_research_backtest_report()
    summary_rows = "\n".join(_research_backtest_summary_rows(report))
    metric_rows = "\n".join(_research_backtest_metric_rows(report))
    excluded_rows = "\n".join(_research_backtest_asset_rows(report.get("excluded_assets", []), empty="No excluded assets recorded"))
    unavailable_rows = "\n".join(_research_backtest_asset_rows(report.get("unavailable_assets", []), empty="No unavailable assets recorded"))
    equity_rows = "\n".join(_research_backtest_equity_rows(report))
    allocation_rows = "\n".join(_research_backtest_allocation_rows(report))
    warning_rows = "\n".join(_message_rows(report.get("warnings", []), empty="No research backtest warnings"))
    benchmark_rows = "\n".join(_research_backtest_benchmark_rows(report))
    sample_rows = "\n".join(_mapping_rows(report.get("diagnostics", {}).get("sample_period", {}), empty="No sample period diagnostics recorded"))
    constraint_rows = "\n".join(_research_backtest_constraint_rows(report))
    factor_rows = "\n".join(_mapping_rows(report.get("diagnostics", {}).get("factor_summary", {}), empty="No factor diagnostics recorded"))
    selection_rows = "\n".join(_research_backtest_selection_rows(report))
    decision_rows = "\n".join(_mapping_rows(report.get("decision", {}), empty="No execution validation decision recorded"))

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Research Backtest</title>
      <style>{_report_page_css()}</style>
    </head>
    <body>
      <header>
        <h1>Research Backtest</h1>
        <p>研究资产层指数回测，不代表 ETF 可执行收益，也不替代 V11 production candidate。<a href="/">Dashboard</a> · <a href="/current-decision">Current Decision</a> · <a href="/research-universe">Research Universe</a> · <a href="/execution-backtest">Execution Backtest</a> · <a href="/shadow-portfolio">Shadow Portfolio</a> · <a href="/production-readiness">Production Readiness</a></p>
      </header>
      <main>
        <section>
          <h2>Status</h2>
          <table><tbody>{summary_rows}</tbody></table>
        </section>
        <section>
          <h2>Metrics</h2>
          <table>
            <thead><tr><th>Metric</th><th>Value</th></tr></thead>
            <tbody>{metric_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Benchmark Comparison</h2>
          <table>
            <thead><tr><th>Strategy</th><th>Annual Return</th><th>Max Drawdown</th><th>Sharpe</th><th>Calmar</th></tr></thead>
            <tbody>{benchmark_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Sample Period Explanation</h2>
          <table><tbody>{sample_rows}</tbody></table>
        </section>
        <section>
          <h2>Constraint Diagnostics</h2>
          <table><tbody>{constraint_rows}</tbody></table>
        </section>
        <section>
          <h2>Factor Summary</h2>
          <table><tbody>{factor_rows}</tbody></table>
        </section>
        <section>
          <h2>Selection Frequency</h2>
          <table>
            <thead><tr><th>Asset</th><th>Selected Months</th></tr></thead>
            <tbody>{selection_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Ready for Execution Backtest?</h2>
          <table><tbody>{decision_rows}</tbody></table>
          <p>This is not executable ETF performance.</p>
        </section>
        <section>
          <h2>Excluded Assets</h2>
          <table>
            <thead><tr><th>Asset</th><th>Reason</th></tr></thead>
            <tbody>{excluded_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Unavailable Assets</h2>
          <table>
            <thead><tr><th>Asset</th><th>Reason</th></tr></thead>
            <tbody>{unavailable_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Equity Curve</h2>
          <table>
            <thead><tr><th>Date</th><th>Value</th></tr></thead>
            <tbody>{equity_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Monthly Allocations</h2>
          <table>
            <thead><tr><th>Date</th><th>Weights</th></tr></thead>
            <tbody>{allocation_rows}</tbody>
          </table>
        </section>
        <section>
          <h2>Warnings</h2>
          <table><tbody>{warning_rows}</tbody></table>
        </section>
      </main>
      {_unified_shell_scripts()}
    </body>
    </html>
    """


@app.get("/execution-backtest", response_class=HTMLResponse)
def execution_backtest_page() -> str:
    report = load_execution_backtest_report()
    audit = load_execution_data_availability_report()
    improvement = load_mapping_improvement_report()
    proxy_research = load_proxy_research_report()
    proposal = load_mapping_proposal_report()
    counterfactual = load_counterfactual_report()
    provenance = load_price_dataset_manifest()
    attribution = load_mapping_attribution_report()
    mapping_review = load_mapping_review_report()
    approval_package = load_mapping_approval_package()
    decision_ledger = load_mapping_decision_ledger()
    approval_record = load_mapping_approval_record()
    metrics = "\n".join(_mapping_rows(report.get("metrics", {}), empty="Execution backtest report not generated yet"))
    overlap = "\n".join(_mapping_rows(report.get("research_overlap_metrics", {}), empty="No research overlap metrics recorded"))
    gap = "\n".join(_mapping_rows(report.get("execution_gap", {}), empty="No execution gap recorded"))
    mapping = "\n".join(_mapping_rows(report.get("mapping_summary", {}), empty="No mapping summary recorded"))
    decision = "\n".join(_mapping_rows(report.get("decision", {}), empty="No execution validation decision recorded"))
    cash = "\n".join(_mapping_rows(report.get("aggregate_cash_breakdown", {}), empty="No aggregate cash breakdown recorded"))
    audit_summary = "\n".join(_mapping_rows({key: audit.get(key) for key in ("provider", "checked_assets", "available_assets", "unavailable_assets", "start", "end")}, empty="No ETF data audit recorded"))
    unmapped = "\n".join(_message_rows([str(row.get("research_asset_id")) for row in report.get("unmapped_assets", [])], empty="No unmapped assets"))
    low_quality = "\n".join(_message_rows([str(row.get("research_asset_id")) for row in report.get("low_quality_proxy_assets", [])], empty="No low quality proxies"))
    improvement_rows = "\n".join(_mapping_rows(improvement, empty="No mapping improvement report recorded"))
    proxy_rows = "\n".join(_proxy_research_rows(proxy_research.get("research_assets", [])))
    proposal_rows = "\n".join(_mapping_rows({"status":proposal.get("status"),"proposal_count":len(proposal.get("proposals",[])),"warnings":proposal.get("warnings",[])}, empty="No mapping proposal recorded"))
    counter_rows = "\n".join(_mapping_rows({"common_period":counterfactual.get("common_comparison_period"),"impact":counterfactual.get("impact"),"decision":counterfactual.get("decision")}, empty="No counterfactual report recorded"))
    provenance_rows = "\n".join(_mapping_rows({key:provenance.get(key) for key in ("provider","return_basis","asset_count","provenance_verified","errors")}, empty="No dataset provenance recorded"))
    attribution_rows = "\n".join(_mapping_rows({"proposal_count":len(attribution.get("proposal_attributions",[])),"full_overlay":attribution.get("full_overlay")}, empty="No proposal attribution recorded"))
    review_rows = "\n".join(_mapping_rows(mapping_review.get("decision",{}), empty="No semantic mapping review recorded"))
    approval_rows = "\n".join(_mapping_rows({"research_asset_id":approval_package.get("research_asset_id"),"proposed_proxy":approval_package.get("proposed_proxy"),"common_comparison_period":approval_package.get("common_comparison_period"),"marginal_deltas":approval_package.get("marginal_deltas"),"ready_for_explicit_human_decision":approval_package.get("ready_for_explicit_human_decision"),"readiness_reasons":approval_package.get("readiness_reasons")}, empty="No selective approval package recorded"))
    exact_rows = "\n".join(_mapping_rows(approval_package.get("exact_drawdown_attribution",{}), empty="No exact drawdown reconciliation recorded"))
    semantic_rows = "\n".join(_mapping_rows(approval_package.get("semantic_evidence",{}), empty="No ETF tracking-index evidence recorded"))
    collision_rows = "\n".join(_mapping_rows(approval_package.get("full_collision_exposure",{}), empty="No existing proxy collision recorded"))
    frozen_rows = "\n".join(_mapping_rows({"policy":decision_ledger.get("policy"),"frozen_count":decision_ledger.get("frozen_count"),"decisions":decision_ledger.get("decisions")}, empty="No frozen mapping decisions recorded"))
    approval_record_rows = "\n".join(_mapping_rows(approval_record, empty="No explicit approval record recorded"))
    approval_notice = ("Formal mapping is applied for execution validation and shadow use only; production approval remains false." if approval_record.get("available") else "No formal mapping has been changed. Explicit human approval is required before updating asset_mapping.json.")
    warnings = "\n".join(_message_rows(report.get("warnings", []), empty="No execution backtest warnings"))
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/><title>Execution Backtest</title><style>{_report_page_css()}</style></head><body><header><h1>Execution Backtest</h1><p>This execution backtest is an ETF proxy validation, not a production trading instruction. <a href="/">Dashboard</a> · <a href="/current-decision">Current Decision</a> · <a href="/research-backtest">Research Backtest</a> · <a href="/research-universe">Research Universe</a> · <a href="/shadow-portfolio">Shadow Portfolio</a></p></header><main>
    <section><h2>Status</h2><table><tbody>{"<tr><td>Available</td><td>" + escape(str(report.get("available", False))) + "</td></tr><tr><td>Data Provider</td><td>" + escape(str(report.get("data_provider", "unknown"))) + "</td></tr><tr><td>Period</td><td>" + escape(str(report.get("period", {}))) + "</td></tr>"}</tbody></table></section>
    <section><h2>Dataset Provenance</h2><table><tbody>{provenance_rows}</tbody></table></section><section><h2>Explicit Mapping Approval Record</h2><p>{escape(approval_notice)}</p><table><tbody>{approval_record_rows}</tbody></table></section><section><h2>Selective Mapping Approval Package</h2><table><tbody>{approval_rows}</tbody></table></section><section><h2>Exact Drawdown Reconciliation</h2><table><tbody>{exact_rows}</tbody></table></section><section><h2>ETF Tracking Index Evidence</h2><table><tbody>{semantic_rows}</tbody></table></section><section><h2>Exposure Differences</h2><table><tbody>{semantic_rows}</tbody></table></section><section><h2>Existing Proxy Collision</h2><table><tbody>{collision_rows}</tbody></table></section><section><h2>Ready for Explicit Human Decision?</h2><table><tbody>{approval_rows}</tbody></table></section><section><h2>Frozen Research-Only and Rejected Proposals</h2><table><tbody>{frozen_rows}</tbody></table></section><section><h2>Real ETF Data Audit</h2><table><tbody>{audit_summary}</tbody></table></section><section><h2>Execution Metrics</h2><table><tbody>{metrics}</tbody></table></section><section><h2>Research Overlap Metrics</h2><table><tbody>{overlap}</tbody></table></section><section><h2>Execution Gap</h2><table><tbody>{gap}</tbody></table></section><section><h2>Mapping Summary</h2><table><tbody>{mapping}</tbody></table></section><section><h2>Aggregate Cash Breakdown</h2><table><tbody>{cash}</tbody></table></section><section><h2>Mapping Proposal</h2><table><tbody>{proposal_rows}</tbody></table></section><section><h2>Per-Proposal Marginal Impact</h2><table><tbody>{attribution_rows}</tbody></table></section><section><h2>Drawdown Attribution</h2><table><tbody>{attribution_rows}</tbody></table></section><section><h2>Full Proxy Collision Exposure</h2><table><tbody>{counter_rows}</tbody></table></section><section><h2>Semantic Mapping Review</h2><p>Statistical correlation alone is not sufficient evidence for an ETF execution mapping.</p><table><tbody>{review_rows}</tbody></table></section><section><h2>Ready for Mapping Update Task?</h2><table><tbody>{review_rows}</tbody></table></section><section><h2>Baseline vs Counterfactual</h2><table><tbody>{counter_rows}</tbody></table></section><section><h2>Unmapped Assets</h2><table><tbody>{unmapped}</tbody></table></section><section><h2>Low Quality Proxies</h2><table><tbody>{low_quality}</tbody></table></section><section><h2>Mapping Improvement</h2><table><tbody>{improvement_rows}</tbody></table></section><section><h2>Proxy Candidate Research</h2><table><tbody>{proxy_rows}</tbody></table></section><section><h2>Ready for Execution Validation?</h2><table><tbody>{decision}</tbody></table></section><section><h2>Warnings</h2><table><tbody>{warnings}</tbody></table></section></main>{_unified_shell_scripts()}</body></html>"""


@app.get("/shadow-portfolio", response_class=HTMLResponse)
def shadow_portfolio_page() -> str:
    report = load_execution_aware_shadow_portfolio()
    approval_integrity = load_approval_integrity_seal()
    transaction_status = load_transaction_status()
    status_rows = "\n".join(_mapping_rows({key:report.get(key) for key in ("available","status","production_approved","source_strategy","source_allocation_date","data_as_of")}, empty="Shadow portfolio report not generated yet"))
    research_rows = "\n".join(_mapping_rows(report.get("research_weights", {}), empty="No research weights recorded"))
    execution_rows = "\n".join(_mapping_rows(report.get("execution_weights", {}), empty="No execution weights recorded"))
    cash_rows = "\n".join(_mapping_rows(report.get("cash_breakdown", {}), empty="No cash breakdown recorded"))
    mapping_rows = "\n".join(_shadow_mapping_rows(report.get("mapping_explanations", [])))
    frozen_rows = "\n".join(_mapping_rows({"research_only":report.get("frozen_research_only_assets", []),"rejected_proxy":report.get("rejected_proxy_assets", [])}, empty="No frozen assets recorded"))
    constraint_rows = "\n".join(_mapping_rows(report.get("constraint_checks", {}), empty="No constraint checks recorded"))
    provenance_rows = "\n".join(_mapping_rows(report.get("data_provenance", {}), empty="No provenance recorded"))
    approval_integrity_rows = "\n".join(_mapping_rows({"available":approval_integrity.get("available"),"verification_status":approval_integrity.get("verification_status"),"seal_hash":approval_integrity.get("seal_hash"),"validation":approval_integrity.get("validation")}, empty="No approval integrity seal recorded"))
    snapshot_rows = "\n".join(_mapping_rows(report.get("snapshot_integrity", {}), empty="No snapshot hashes recorded"))
    price_as_of_rows = "\n".join(_mapping_rows(report.get("price_as_of_by_proxy", {}), empty="No price as-of records"))
    transaction_rows = "\n".join(_mapping_rows({"status":transaction_status.get("status"),"pending":transaction_status.get("pending"),"commit_marker":transaction_status.get("commit_marker"),"errors":transaction_status.get("errors")}, empty="No transaction status recorded"))
    warning_rows = "\n".join(_message_rows(report.get("warnings", []), empty="No warnings recorded"))
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>Execution-Aware Shadow Portfolio</title><style>{_report_page_css()}</style></head><body><header><h1>Execution-Aware Shadow Portfolio</h1><p>This is an experimental execution-aware shadow allocation. It is not a production portfolio or trading instruction. <a href="/">Dashboard</a> · <a href="/current-decision">Current Decision</a> · <a href="/research-backtest">Research Backtest</a> · <a href="/execution-backtest">Execution Backtest</a></p></header><main><section><h2>Shadow Status</h2><table><tbody>{status_rows}</tbody></table></section><section><h2>Approval Integrity</h2><table><tbody>{approval_integrity_rows}</tbody></table></section><section><h2>Snapshot Hashes</h2><table><tbody>{snapshot_rows}</tbody></table></section><section><h2>Price As-Of by Proxy</h2><table><tbody>{price_as_of_rows}</tbody></table></section><section><h2>Transaction Status</h2><table><tbody>{transaction_rows}</tbody></table></section><section><h2>Source Research Allocation</h2><table><tbody>{research_rows}</tbody></table></section><section><h2>Research Weights</h2><table><tbody>{research_rows}</tbody></table></section><section><h2>Executable ETF Weights</h2><table><tbody>{execution_rows}</tbody></table></section><section><h2>Cash Breakdown</h2><table><tbody>{cash_rows}</tbody></table></section><section><h2>Mapping Explanations</h2><table><thead><tr><th>Research Asset</th><th>Weight</th><th>Destination</th><th>Quality</th><th>Decision</th><th>Reason</th></tr></thead><tbody>{mapping_rows}</tbody></table></section><section><h2>Frozen Research-Only Assets</h2><table><tbody>{frozen_rows}</tbody></table></section><section><h2>Constraint Checks</h2><table><tbody>{constraint_rows}</tbody></table></section><section><h2>Data Provenance</h2><table><tbody>{provenance_rows}</tbody></table></section><section><h2>V11 Boundary</h2><p>V11 remains the existing production candidate. This shadow allocation does not replace or modify V11.</p></section><section><h2>Warnings</h2><table><tbody>{warning_rows}</tbody></table></section></main>{_unified_shell_scripts()}</body></html>"""


@app.get("/v11-current-allocation", response_class=HTMLResponse)
def v11_current_allocation_page() -> str:
    report = load_release_json("v11_current_allocation.json")
    status_rows = "\n".join(
        _mapping_rows(
            {
                key: report.get(key)
                for key in (
                    "available",
                    "status",
                    "strategy",
                    "as_of",
                    "source_state_date",
                    "production_candidate",
                    "production_actionable",
                    "trading_instruction",
                )
            },
            empty="V11 current allocation snapshot not generated yet",
        )
    )
    allocation_rows = "\n".join(
        _mapping_rows(report.get("allocation", {}), empty="No V11 allocation available")
    )
    equity_cash_rows = "\n".join(
        _mapping_rows(
            {
                "equity_weight": report.get("equity_weight"),
                "cash_weight": report.get("cash_weight"),
            },
            empty="No V11 equity or cash weight available",
        )
    )
    regime_rows = "\n".join(
        _mapping_rows(report.get("regime", {}), empty="No V11 regime recorded")
    )
    risk_rows = "\n".join(
        _mapping_rows(
            report.get("risk_budget", {}), empty="No V11 risk budget recorded"
        )
    )
    exposure_rows = "\n".join(
        _mapping_rows(
            report.get("exposure_decision", {}),
            empty="No V11 exposure decision recorded",
        )
    )
    selected_rows = "\n".join(
        _message_rows(
            report.get("selected_assets", []), empty="No V11 assets selected"
        )
    )
    actual_target_rows = "\n".join(
        _mapping_rows(
            {
                "actual_weights_percent": report.get("allocation_percent", {}),
                "target_weights_percent": report.get("target_weights_percent", {}),
            },
            empty="No actual or target V11 weights recorded",
        )
    )
    assumption_rows = "\n".join(
        _mapping_rows(
            report.get("assumptions", {}), empty="No V11 assumptions recorded"
        )
    )
    integrity_rows = "\n".join(
        _mapping_rows(
            report.get("source_integrity", {}),
            empty="No V11 source integrity recorded",
        )
    )
    semantic_integrity_rows = "\n".join(
        _mapping_rows(
            {
                key: report.get("source_integrity", {}).get(key)
                for key in (
                    "verified",
                    "semantic_verified",
                    "errors",
                )
            },
            empty="No V11 semantic integrity result recorded",
        )
    )
    payload_hash_rows = "\n".join(
        _mapping_rows(
            {
                key: report.get("source_integrity", {}).get(key)
                for key in (
                    "snapshot_payload_hash",
                    "actual_snapshot_payload_hash",
                )
            },
            empty="No V11 snapshot payload hash recorded",
        )
    )
    constraint_rows = "\n".join(
        _mapping_rows(
            report.get("constraint_checks", {}),
            empty="No V11 constraint checks recorded",
        )
    )
    warning_rows = "\n".join(
        _message_rows(report.get("warnings", []), empty="No warnings recorded")
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>V11 Current Allocation</title><style>{_report_page_css()}</style></head><body><header><h1>V11 Current Allocation</h1><p>This is an offline V11 model allocation snapshot. It is not an order or trading instruction.</p><p><a href="/">Dashboard</a> · <a href="/current-decision">Current Decision</a> · <a href="/diagnosis">Strategy Diagnosis</a> · <a href="/production-readiness">Production Readiness</a></p></header><main><section><h2>Snapshot Status</h2><table><tbody>{status_rows}</tbody></table></section><section><h2>V11 Allocation</h2><table><tbody>{allocation_rows}</tbody></table></section><section><h2>Equity / Cash Weight</h2><table><tbody>{equity_cash_rows}</tbody></table></section><section><h2>Regime</h2><table><tbody>{regime_rows}</tbody></table></section><section><h2>Risk Budget</h2><table><tbody>{risk_rows}</tbody></table></section><section><h2>Exposure Decision</h2><table><tbody>{exposure_rows}</tbody></table></section><section><h2>Selected Assets</h2><table><tbody>{selected_rows}</tbody></table></section><section><h2>Actual Weights vs Target Weights</h2><table><tbody>{actual_target_rows}</tbody></table></section><section><h2>Canonical Assumptions</h2><table><tbody>{assumption_rows}</tbody></table></section><section><h2>Source Integrity</h2><table><tbody>{integrity_rows}</tbody></table></section><section><h2>Snapshot Semantic Integrity</h2><table><tbody>{semantic_integrity_rows}</tbody></table></section><section><h2>Snapshot Payload Hash</h2><table><tbody>{payload_hash_rows}</tbody></table></section><section><h2>Constraint Checks</h2><table><tbody>{constraint_rows}</tbody></table></section><section><h2>Non-Trading Warning</h2><table><tbody>{warning_rows}</tbody></table></section></main>{_unified_shell_scripts()}</body></html>"""


@app.get("/current-decision", response_class=HTMLResponse)
def current_decision_page() -> str:
    report = load_release_json("current_market_decision.json")
    market_rows = "\n".join(_mapping_rows(report.get("market_state", {}), empty="Current market state report not generated yet"))
    risk_rows = "\n".join(_mapping_rows(report.get("risk_summary", {}), empty="No risk summary recorded"))
    v11_rows = "\n".join(_mapping_rows(report.get("production_candidate", {}), empty="No V11 candidate snapshot recorded"))
    v11_allocation_rows = "\n".join(_mapping_rows(report.get("production_candidate", {}).get("allocation", {}), empty="No V11 current allocation available"))
    v11_equity_cash_rows = "\n".join(_mapping_rows({key: report.get("production_candidate", {}).get(key) for key in ("equity_weight", "cash_weight")}, empty="No V11 equity or cash weights available"))
    v11_selected_rows = "\n".join(_message_rows(report.get("production_candidate", {}).get("selected_assets", []), empty="No V11 selected assets available"))
    v11_difference_rows = "\n".join(_mapping_rows(report.get("comparison", {}).get("weight_differences", {}), empty="No V11 and Shadow weight differences available"))
    v11_integrity_rows = "\n".join(_mapping_rows(report.get("production_candidate", {}).get("allocation_integrity", {}), empty="No V11 snapshot integrity available"))
    identifier_namespace_rows = "\n".join(_mapping_rows({"identifier_namespace": report.get("comparison", {}).get("identifier_namespace")}, empty="No instrument identifier namespace recorded"))
    identifier_status_rows = "\n".join(_mapping_rows({key: report.get("comparison", {}).get(key) for key in ("identifier_normalization_verified", "identifier_errors")}, empty="No instrument identifier normalization result recorded"))
    canonical_v11_rows = "\n".join(_mapping_rows(report.get("comparison", {}).get("v11_canonical_weights", {}), empty="No canonical V11 weights available"))
    unresolved_identifier_rows = "\n".join(_mapping_rows({"unresolved_v11_ids": report.get("comparison", {}).get("unresolved_v11_ids", []), "unresolved_shadow_ids": report.get("comparison", {}).get("unresolved_shadow_ids", [])}, empty="No unresolved instrument identifiers"))
    research_rows = "\n".join(_mapping_rows(report.get("research_allocation", {}), empty="No research allocation recorded"))
    shadow_rows = "\n".join(_mapping_rows(report.get("execution_shadow", {}), empty="No execution-aware shadow allocation recorded"))
    validation_rows = "\n".join(_mapping_rows(report.get("execution_validation", {}), empty="No execution validation status recorded"))
    freshness_rows = "\n".join(_mapping_rows(report.get("data_freshness", {}), empty="No freshness checks recorded"))
    provenance_rows = "\n".join(_mapping_rows(report.get("source_manifest", {}), empty="No source provenance recorded"))
    source_status_rows = "\n".join(_mapping_rows(report.get("source_hash_verification", {}), empty="No required source verification recorded"))
    gate_policy_rows = "\n".join(_mapping_rows(report.get("execution_validation", {}).get("gate_policy", {}), empty="No execution gate policy recorded"))
    v11_availability_rows = "\n".join(_mapping_rows({key: report.get("production_candidate", {}).get(key) for key in ("candidate_metadata_available", "current_allocation_available", "boundary_verified", "unchanged")}, empty="No V11 boundary status recorded"))
    decision_date_rows = "\n".join(_mapping_rows({key: report.get(key) for key in ("decision_date", "generated_at")}, empty="No decision date recorded"))
    market_date_rows = "\n".join(_mapping_rows({"market_data_as_of": report.get("market_data_as_of")}, empty="No market data cutoff recorded"))
    governance_date_rows = "\n".join(_mapping_rows({"governance_state_as_of": report.get("governance_state_as_of")}, empty="No governance state date recorded"))
    snapshot_mode_rows = "\n".join(_mapping_rows({"snapshot_mode": report.get("snapshot_mode")}, empty="No snapshot mode recorded"))
    summary = report.get("decision_summary", {})
    summary_headline = escape(
        decision_headline(
            status=str(report.get("status", "unavailable")),
            ready_for_user_review=report.get("ready_for_user_review") is True,
        )
    )
    executable_rows = "\n".join(_message_rows(summary.get("what_is_executable", []), empty="No ETF allocation is production executable"))
    research_only_rows = "\n".join(_message_rows(summary.get("what_is_not_executable", []), empty="No research-only assets recorded"))
    blocking_rows = "\n".join(_message_rows(summary.get("blocking_conditions", []), empty="No data-integrity blockers; execution validation gates still apply"))
    constraint_rows = "\n".join(_message_rows(report.get("risk_summary", {}).get("key_risks", []), empty="No current constraints recorded"))
    status_rows = "\n".join(_mapping_rows({key: report.get(key) for key in ("available", "status", "ready_for_user_review", "production_actionable")}, empty="Current decision report not generated yet"))
    cash_text = escape(str(report.get("cash_explanation", "Cash explanation unavailable")))
    decision_date = escape(str(report.get("decision_date", "unavailable")))
    market_data_as_of = escape(str(report.get("market_data_as_of", "unavailable")))
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>Current Market Decision</title><style>{_report_page_css()}</style></head><body><header><h1>Current Market Decision</h1><p>Decision prepared on {decision_date} using market data through {market_data_as_of}. This page does not create orders or replace V11.</p><p><a href="/">Dashboard</a> · <a href="/v11-current-allocation">V11 Current Allocation</a> · <a href="/research-backtest">Research Backtest</a> · <a href="/execution-backtest">Execution Backtest</a> · <a href="/shadow-portfolio">Shadow Portfolio</a></p></header><main><section><h2>Decision Status</h2><table><tbody>{status_rows}</tbody></table></section><section><h2>Decision Summary</h2><p>{summary_headline}</p></section><section><h2>Decision Date</h2><table><tbody>{decision_date_rows}</tbody></table></section><section><h2>Market Data Through</h2><table><tbody>{market_date_rows}</tbody></table></section><section><h2>Governance State Date</h2><table><tbody>{governance_date_rows}</tbody></table></section><section><h2>Snapshot Mode</h2><table><tbody>{snapshot_mode_rows}</tbody></table></section><section><h2>Current Market State</h2><table><tbody>{market_rows}</tbody></table></section><section><h2>Risk Level</h2><table><tbody>{risk_rows}</tbody></table></section><section><h2>V11 Production Candidate</h2><table><tbody>{v11_rows}</tbody></table></section><section><h2>V11 Metadata Available</h2><table><tbody>{v11_availability_rows}</tbody></table></section><section><h2>V11 Current Allocation Available</h2><table><tbody>{v11_availability_rows}</tbody></table></section><section><h2>V11 Current Allocation</h2><table><tbody>{v11_allocation_rows}</tbody></table></section><section><h2>V11 Equity and Cash</h2><table><tbody>{v11_equity_cash_rows}</tbody></table></section><section><h2>V11 Selected Assets</h2><table><tbody>{v11_selected_rows}</tbody></table></section><section><h2>Instrument Identifier Namespace</h2><table><tbody>{identifier_namespace_rows}</tbody></table></section><section><h2>Identifier Normalization Status</h2><table><tbody>{identifier_status_rows}</tbody></table></section><section><h2>Canonical V11 Weights</h2><table><tbody>{canonical_v11_rows}</tbody></table></section><section><h2>Unresolved Instrument IDs</h2><table><tbody>{unresolved_identifier_rows}</tbody></table></section><section><h2>V11 vs Shadow Weight Differences</h2><table><tbody>{v11_difference_rows}</tbody></table></section><section><h2>V11 Snapshot Integrity</h2><table><tbody>{v11_integrity_rows}</tbody></table></section><section><h2>Research Allocation</h2><table><tbody>{research_rows}</tbody></table></section><section><h2>Execution-Aware Shadow Allocation</h2><table><tbody>{shadow_rows}</tbody></table></section><section><h2>Why 40% Cash?</h2><p>{cash_text}</p></section><section><h2>Execution Validation Status</h2><table><tbody>{validation_rows}</tbody></table></section><section><h2>Execution Gate Policy</h2><table><tbody>{gate_policy_rows}</tbody></table></section><section><h2>Current Constraints</h2><table><tbody>{constraint_rows}</tbody></table></section><section><h2>Data Freshness</h2><table><tbody>{freshness_rows}</tbody></table></section><section><h2>Required Source Status</h2><table><tbody>{source_status_rows}</tbody></table></section><section><h2>Source Provenance</h2><table><tbody>{provenance_rows}</tbody></table></section><section><h2>What Is Executable</h2><p>These are eligible ETF proxy weights in a shadow snapshot only; they are not orders.</p><table><tbody>{executable_rows}</tbody></table></section><section><h2>What Is Research-Only</h2><table><tbody>{research_only_rows}</tbody></table></section><section><h2>Blocking Conditions</h2><table><tbody>{blocking_rows}</tbody></table></section><section><h2>V11 vs Shadow Boundary</h2><p>V11 remains unchanged. The Research allocation and Execution-Aware Shadow are shown side by side only; no merged portfolio is created and Shadow cannot substitute for an unavailable V11 allocation.</p></section></main>{_unified_shell_scripts()}</body></html>"""


def _shadow_mapping_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ['<tr><td colspan="6">No mapping explanations recorded</td></tr>']
    return [
        "<tr>"
        f"<td>{escape(str(row.get('research_asset_id', '')))}</td>"
        f"<td>{escape(str(row.get('research_weight', '')))}</td>"
        f"<td>{escape(str(row.get('destination', '')))}</td>"
        f"<td>{escape(str(row.get('mapping_quality', '')))}</td>"
        f"<td>{escape(str(row.get('decision_status', '')))}</td>"
        f"<td>{escape(str(row.get('reason', '')))}</td>"
        "</tr>"
        for row in rows
    ]


def _research_universe_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        allocation = "yes" if item.get("eligible_for_allocation") else "no"
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("name", "")))}<span>{escape(str(item.get("asset_id", "")))}</span></td>
              <td>{escape(str(item.get("role", "")))}</td>
              <td>{escape(str(item.get("category", "")))}</td>
              <td>{escape(str(item.get("sleeve", "")))}</td>
              <td>{escape(str(item.get("data_api", "")))}</td>
              <td>{escape(str(item.get("return_basis", "")))}</td>
              <td>{allocation}</td>
            </tr>
            """
        )
    return html_rows


def _execution_universe_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        start = item.get("investable_start_date") or "pending audit"
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("name", "")))}<span>{escape(str(item.get("asset_id", "")))}</span></td>
              <td>{escape(str(item.get("data_api", "")))}</td>
              <td>{escape(str(item.get("return_basis", "")))}</td>
              <td>{escape(str(start))}</td>
              <td>{escape(str(item.get("notes", "")))}</td>
            </tr>
            """
        )
    return html_rows


def _asset_mapping_rows(rows: list[dict]) -> list[str]:
    html_rows: list[str] = []
    for item in rows:
        proxies = ", ".join(item.get("execution_proxies") or [])
        primary = item.get("primary_execution_proxy") or "-"
        html_rows.append(
            f"""
            <tr>
              <td>{escape(str(item.get("research_asset_name", "")))}<span>{escape(str(item.get("research_asset_id", "")))}</span></td>
              <td>{escape(str(primary))}</td>
              <td>{escape(proxies or "-")}</td>
              <td>{escape(str(item.get("mapping_quality", "")))}</td>
              <td>{escape(str(item.get("notes", "")))}</td>
            </tr>
            """
        )
    return html_rows


def _proxy_research_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["<tr><td colspan=\"2\">No proxy candidate research recorded</td></tr>"]
    html_rows = []
    for row in rows:
        top = (row.get("candidate_rankings") or [{}])[0]
        recommendation = row.get("recommendation", {})
        html_rows.append(f"<tr><td>{escape(str(row.get('research_asset_id')))}</td><td>{escape(str(top.get('candidate_id')))} score={escape(str(top.get('score')))} correlation={escape(str(top.get('correlation')))} tracking_error={escape(str(top.get('tracking_error_annualized')))} action={escape(str(recommendation.get('action')))} manual_approval={escape(str(recommendation.get('requires_manual_approval')))}</td></tr>")
    return html_rows


def _count_rows(counts: dict[str, int]) -> list[str]:
    if not counts:
        return ["<tr><td colspan=\"2\">No counts recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(label))}</td>
          <td>{int(count)}</td>
        </tr>
        """
        for label, count in counts.items()
    ]


def _message_rows(messages: list[str], *, empty: str) -> list[str]:
    if not messages:
        return [f"<tr><td>{escape(empty)}</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(message)}</td>
        </tr>
        """
        for message in messages
    ]


def _data_availability_summary_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return [
            f"""
            <tr>
              <td>Status</td>
              <td>{escape(str(report.get("message", "Data audit not generated yet. Run scripts/audit_research_universe.py.")))}</td>
            </tr>
            """
        ]
    return [
        f"<tr><td>Report</td><td>{escape(str(report.get('report_path', '')))}</td></tr>",
        f"<tr><td>Provider</td><td>{escape(str(report.get('provider', '')))}</td></tr>",
        f"<tr><td>Checked Assets</td><td>{int(report.get('checked_assets', 0))}</td></tr>",
        f"<tr><td>Available Assets</td><td>{int(report.get('available_assets', 0))}</td></tr>",
        f"<tr><td>Unavailable Assets</td><td>{int(report.get('unavailable_assets', 0))}</td></tr>",
        f"<tr><td>Warnings</td><td>{len(report.get('warnings', []))}</td></tr>",
        f"<tr><td>Errors</td><td>{len(report.get('errors', []))}</td></tr>",
    ]


def _data_availability_api_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return ["<tr><td colspan=\"3\">Data audit not generated yet. Run scripts/audit_research_universe.py.</td></tr>"]
    rows = []
    for data_api, counts in report.get("available_by_data_api", {}).items():
        rows.append(
            f"""
            <tr>
              <td>{escape(str(data_api))}</td>
              <td>{int(counts.get("available", 0))}</td>
              <td>{int(counts.get("unavailable", 0))}</td>
            </tr>
            """
        )
    return rows or ["<tr><td colspan=\"3\">No data API availability recorded</td></tr>"]


def _unavailable_data_asset_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return ["<tr><td colspan=\"3\">Data audit not generated yet. Run scripts/audit_research_universe.py.</td></tr>"]
    rows = [
        row for row in report.get("rows", [])
        if not row.get("available")
    ]
    if not rows:
        return ["<tr><td colspan=\"3\">No unavailable assets recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(row.get("name", "")))}<span>{escape(str(row.get("asset_id", "")))}</span></td>
          <td>{escape(str(row.get("data_api", "")))}</td>
          <td>{escape(str(row.get("error", "")))}</td>
        </tr>
        """
        for row in rows
    ]


def _data_audit_warning_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return ["<tr><td>Data audit not generated yet. Run scripts/audit_research_universe.py.</td></tr>"]
    warnings = report.get("warnings", [])
    if not warnings:
        return ["<tr><td>No data audit warnings</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(warning))}</td>
        </tr>
        """
        for warning in warnings[:50]
    ]


def _metadata_suggestion_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return [
            f"<tr><td colspan=\"4\">{escape(str(report.get('message', 'Metadata suggestions not generated yet.')))}</td></tr>"
        ]
    rows = report.get("suggestions", [])
    if not rows:
        return ["<tr><td colspan=\"4\">No metadata suggestions recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(row.get("name", "")))}<span>{escape(str(row.get("asset_id", "")))}</span></td>
          <td>{escape(str(row.get("data_start_date", "")))}</td>
          <td>{escape(str(row.get("investable_start_date", "")))}</td>
          <td>{escape(str(row.get("confidence", "")))}</td>
        </tr>
        """
        for row in rows[:50]
    ]


def _blocked_metadata_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return [
            f"<tr><td colspan=\"2\">{escape(str(report.get('message', 'Metadata suggestions not generated yet.')))}</td></tr>"
        ]
    rows = report.get("blocked_assets", [])
    if not rows:
        return ["<tr><td colspan=\"2\">No blocked metadata assets recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(row.get("name", "")))}<span>{escape(str(row.get("asset_id", "")))}</span></td>
          <td>{escape(str(row.get("reason", "")))}</td>
        </tr>
        """
        for row in rows
    ]


def _return_basis_summary_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return [
            f"<tr><td>Status</td><td>{escape(str(report.get('message', 'Return basis review not generated yet.')))}</td></tr>"
        ]
    return [
        f"<tr><td>Report</td><td>{escape(str(report.get('report_path', '')))}</td></tr>",
        f"<tr><td>Registered Total Return Available</td><td>{len(report.get('registered_total_return_available', []))}</td></tr>",
        f"<tr><td>Basis Confirmed Total Return</td><td>{len(report.get('basis_confirmed_total_return', []))}</td></tr>",
        f"<tr><td>Provider Metadata Mismatch</td><td>{len(report.get('provider_metadata_mismatch', []))}</td></tr>",
        f"<tr><td>Needs Manual Review</td><td>{len(report.get('needs_manual_review', []))}</td></tr>",
        f"<tr><td>Unavailable Total Return</td><td>{len(report.get('unavailable_total_return', []))}</td></tr>",
        f"<tr><td>Price Index Monitor Assets</td><td>{len(report.get('price_index_monitor_assets', []))}</td></tr>",
        "<tr><td>399606.SZ</td><td>Manual return-basis confirmation required until the real source return basis is confirmed</td></tr>",
    ]


def _review_asset_rows(report: dict, key: str) -> list[str]:
    if not report.get("available"):
        return [
            f"<tr><td colspan=\"4\">{escape(str(report.get('message', 'Return basis review not generated yet.')))}</td></tr>"
        ]
    rows = report.get(key, [])
    if not rows:
        return ["<tr><td colspan=\"4\">No assets recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(row.get("name", "")))}<span>{escape(str(row.get("asset_id", "")))}</span></td>
          <td>{escape(str(row.get("return_basis", "")))}</td>
          <td>{escape("available" if row.get("available") else "unavailable")}</td>
          <td>{escape(str(row.get("reason", "")))}</td>
        </tr>
        """
        for row in rows[:50]
    ]


def _readiness_summary_rows(readiness: dict) -> list[str]:
    return [
        f"<tr><td>Ready For Research Backtest</td><td>{escape(str(readiness.get('ready_for_research_backtest', False)))}</td></tr>",
        f"<tr><td>Eligible Assets</td><td>{int(readiness.get('eligible_assets', 0))}</td></tr>",
        f"<tr><td>Blocked Assets</td><td>{len(readiness.get('blocked_assets', []))}</td></tr>",
        f"<tr><td>Warnings</td><td>{len(readiness.get('warnings', []))}</td></tr>",
    ]


def _readiness_check_rows(readiness: dict) -> list[str]:
    checks = readiness.get("checks", {})
    if not checks:
        return ["<tr><td colspan=\"2\">No readiness checks recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(name))}</td>
          <td>{escape(str(value))}</td>
        </tr>
        """
        for name, value in checks.items()
    ]


def _readiness_blocked_rows(readiness: dict) -> list[str]:
    rows = readiness.get("blocked_assets", [])
    if not rows:
        return ["<tr><td colspan=\"2\">No blocked assets recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(row.get("name", "")))}<span>{escape(str(row.get("asset_id", "")))}</span></td>
          <td>{escape(str(row.get("reason", "")))}</td>
        </tr>
        """
        for row in rows
    ]


def _research_backtest_summary_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return [
            f"<tr><td>Status</td><td>{escape(str(report.get('message', 'research backtest report not generated yet')))}</td></tr>"
        ]
    period = report.get("period", {})
    return [
        f"<tr><td>Report</td><td>{escape(str(report.get('report_path', '')))}</td></tr>",
        f"<tr><td>Strategy</td><td>{escape(str(report.get('strategy', '')))}</td></tr>",
        f"<tr><td>Universe Count</td><td>{int(report.get('universe_count', 0))}</td></tr>",
        f"<tr><td>Period</td><td>{escape(str(period.get('start')))} to {escape(str(period.get('end')))}</td></tr>",
        "<tr><td>Production Relation</td><td>This research backtest does not replace the current V11 production candidate.</td></tr>",
    ]


def _research_backtest_metric_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return ["<tr><td colspan=\"2\">Research backtest report not generated yet</td></tr>"]
    metrics = report.get("metrics", {})
    if not metrics:
        return ["<tr><td colspan=\"2\">No metrics recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(name))}</td>
          <td>{escape(str(value))}</td>
        </tr>
        """
        for name, value in metrics.items()
    ]


def _research_backtest_benchmark_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return ["<tr><td colspan=\"5\">Research backtest report not generated yet</td></tr>"]
    rows = report.get("benchmark", {}).get("rows", [])
    if not rows:
        return ["<tr><td colspan=\"5\">No benchmark comparison recorded</td></tr>"]
    return [
        f"<tr><td>{escape(str(row.get('strategy', '')))}</td><td>{escape(str(row.get('annual_return', '')))}</td><td>{escape(str(row.get('max_drawdown', '')))}</td><td>{escape(str(row.get('sharpe', '')))}</td><td>{escape(str(row.get('calmar', '')))}</td></tr>"
        for row in rows
    ]


def _research_backtest_constraint_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return ["<tr><td colspan=\"2\">Research backtest report not generated yet</td></tr>"]
    diagnostics = report.get("constraint_diagnostics", {})
    values = {
        "Violations": len(diagnostics.get("violations", [])),
        **{f"Cash Drag: {key}": value for key, value in diagnostics.get("cash_drag", {}).items()},
        **{f"Cap Hits: {key}": value for key, value in diagnostics.get("cap_hits", {}).items()},
    }
    return _mapping_rows(values, empty="No constraint diagnostics recorded")


def _research_backtest_selection_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return ["<tr><td colspan=\"2\">Research backtest report not generated yet</td></tr>"]
    rows = report.get("diagnostics", {}).get("selection_frequency", [])
    if not rows:
        return ["<tr><td colspan=\"2\">No selection frequency recorded</td></tr>"]
    return [
        f"<tr><td>{escape(str(row.get('name', '')))}<span>{escape(str(row.get('asset_id', '')))}</span></td><td>{int(row.get('selected_months', 0))}</td></tr>"
        for row in rows[:30]
    ]


def _mapping_rows(values: dict, *, empty: str) -> list[str]:
    if not values:
        return [f"<tr><td colspan=\"2\">{escape(empty)}</td></tr>"]
    return [
        f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>"
        for key, value in values.items()
    ]


def _research_backtest_asset_rows(rows: list[dict], *, empty: str) -> list[str]:
    if not rows:
        return [f"<tr><td colspan=\"2\">{escape(empty)}</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(row.get("name", "")))}<span>{escape(str(row.get("asset_id", "")))}</span></td>
          <td>{escape(str(row.get("reason", "")))}</td>
        </tr>
        """
        for row in rows[:100]
    ]


def _research_backtest_equity_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return ["<tr><td colspan=\"2\">Research backtest report not generated yet</td></tr>"]
    rows = report.get("equity_curve", [])[-20:]
    if not rows:
        return ["<tr><td colspan=\"2\">No equity curve recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(row.get("date", "")))}</td>
          <td>{float(row.get("value", 0.0)):.4f}</td>
        </tr>
        """
        for row in rows
    ]


def _research_backtest_allocation_rows(report: dict) -> list[str]:
    if not report.get("available"):
        return ["<tr><td colspan=\"2\">Research backtest report not generated yet</td></tr>"]
    rows = report.get("monthly_allocations", [])[-12:]
    if not rows:
        return ["<tr><td colspan=\"2\">No monthly allocations recorded</td></tr>"]
    return [
        f"""
        <tr>
          <td>{escape(str(row.get("date", "")))}</td>
          <td>{escape(_format_weight_map(row.get("weights", {})))}</td>
        </tr>
        """
        for row in rows
    ]


def _format_weight_map(weights: dict) -> str:
    if not weights:
        return "-"
    return ", ".join(
        f"{asset_id}: {float(weight) * 100:.1f}%"
        for asset_id, weight in sorted(weights.items())
    )


def _format_optional_percent(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return escape(str(value))


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
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if _strategy_diagnosis_report_is_current(report):
            return report
    connection = connect_database(":memory:")
    repository = MarketDataRepository(connection)
    return build_strategy_diagnosis_report(repository, provider_name="mock", report_path=None)


def _strategy_diagnosis_report_is_current(report: dict) -> bool:
    versions = {
        row.get("version")
        for row in report.get("versions", {}).get("rows", [])
    }
    diagnosis = report.get("diagnosis", {})
    return (
        "V10_ROBUST_EXPOSURE" in versions
        and "V11_PRODUCTION_FUSION" in versions
        and "validation" in report.get("benchmark", {})
        and "attribution_v3" in diagnosis
        and "attribution_v9" in diagnosis
        and "attribution_v10" in diagnosis
        and "attribution_v11" in diagnosis
        and "selection_attribution" in diagnosis
        and "selection_analysis" in diagnosis
        and "adaptive_selection" in diagnosis
        and "adaptive_selection_attribution" in diagnosis
        and "exposure_selection_attribution" in diagnosis
        and "robust_exposure_attribution" in diagnosis
        and "production_fusion_attribution" in diagnosis
        and "exposure_analysis" in diagnosis
        and "strategy_selection" in diagnosis
        and "robustness" in diagnosis
        and "stress" in diagnosis
        and "final_strategy" in diagnosis
        and "production_readiness" in diagnosis
        and "stock_breadth" in diagnosis
        and "walk_forward" in diagnosis
        and "promotion" in diagnosis
        and "regime_v3" in diagnosis
        and "strategy_registry" in report
    )


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
