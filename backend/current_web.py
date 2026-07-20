from __future__ import annotations

from html import escape
import json
from pathlib import Path
from string import Template
from typing import Any, Callable

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "current"
P2_REPORT_DIR = ROOT / "data" / "strategy_style_walk_forward_v1"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
REPORT_NAMES = ("research", "allocation", "shadow", "data_status", "manifest")
P2_REPORT_NAMES = ("manifest", "walk_forward_summary")

router = APIRouter()


class CurrentReportsUnavailable(RuntimeError):
    pass


class StrategyResultUnavailable(RuntimeError):
    pass


def _read_template(name: str) -> Template:
    return Template((TEMPLATE_DIR / name).read_text(encoding="utf-8"))


def load_current_reports(report_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    root = report_dir or REPORT_DIR
    reports: dict[str, dict[str, Any]] = {}
    for name in REPORT_NAMES:
        path = root / f"{name}.json"
        if not path.is_file():
            raise CurrentReportsUnavailable(f"缺少当前报告：{path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CurrentReportsUnavailable(f"当前报告无法读取：{path.name}") from exc
        if not isinstance(payload, dict):
            raise CurrentReportsUnavailable(f"当前报告格式无效：{path.name}")
        reports[name] = payload
    status = reports["data_status"]
    if status.get("status") != "success" or status.get("current") is not True:
        raise CurrentReportsUnavailable("数据更新失败，CURRENT_TAA 当前不可用")
    return reports


def load_current_strategy(report_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    return load_current_reports(report_dir)


def load_p2_strategy(artifact_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    root = artifact_dir or P2_REPORT_DIR
    reports: dict[str, dict[str, Any]] = {}
    for name in P2_REPORT_NAMES:
        path = root / f"{name}.json"
        if not path.is_file():
            raise StrategyResultUnavailable(f"缺少 P2 研究结果：{path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StrategyResultUnavailable(f"P2 研究结果无法读取：{path.name}") from exc
        if not isinstance(payload, dict):
            raise StrategyResultUnavailable(f"P2 研究结果格式无效：{path.name}")
        reports[name] = payload

    manifest = reports["manifest"]
    summary = reports["walk_forward_summary"]
    if manifest.get("artifact_set_id") != "STRATEGY_STYLE_WALK_FORWARD_ARTIFACT_V1":
        raise StrategyResultUnavailable("P2 manifest 身份不匹配")
    if summary.get("dataset_id") != "STRATEGY_STYLE_WALK_FORWARD_SUMMARY_V1":
        raise StrategyResultUnavailable("P2 summary 身份不匹配")
    if manifest.get("mechanism_decision") != summary.get("mechanism_decision"):
        raise StrategyResultUnavailable("P2 manifest 与 summary 结论不一致")
    if manifest.get("mechanism_decision") != "REJECTED":
        raise StrategyResultUnavailable("P2 研究结论不是已确认的否决状态")
    if manifest.get("selected_profile") is not None or summary.get("selected_profile") is not None:
        raise StrategyResultUnavailable("P2 研究结果存在未声明的入选 Profile")
    statuses = manifest.get("statuses", {})
    expected = {
        "integration_status": "DO_NOT_INTEGRATE",
        "allocation_status": "NOT_DEFINED",
        "backtest_status": "NOT_RUN",
    }
    if not isinstance(statuses, dict) or any(statuses.get(key) != value for key, value in expected.items()):
        raise StrategyResultUnavailable("P2 下游禁用状态不一致")
    profiles = summary.get("profile_decisions")
    if not isinstance(profiles, list) or len(profiles) != 3:
        raise StrategyResultUnavailable("P2 Profile 结果不完整")
    return reports


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "不可用"


def _num(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "不可用"


def _text(value: Any, fallback: str = "不可用") -> str:
    return escape(str(value if value not in (None, "") else fallback))


def _weight_bar(weight: Any) -> str:
    try:
        width = max(0.0, min(100.0, float(weight) * 100))
    except (TypeError, ValueError):
        width = 0.0
    return f'<span class="weight-bar"><i style="width:{width:.2f}%"></i></span>'


def _metric(label: str, value: str, detail: str = "") -> str:
    return (
        '<div class="metric"><span class="metric-label">'
        f"{escape(label)}</span><strong>{escape(value)}</strong>"
        f'<small>{escape(detail)}</small></div>'
    )


def _chart(series: list[dict[str, Any]], label: str, benchmark: list[dict[str, Any]] | None = None) -> str:
    payload = [{"label": label, "color": "#147d64", "points": series}]
    if benchmark is not None:
        payload.append({"label": "510500 南方中证500ETF（同期市场背景）", "color": "#c2532d", "points": benchmark})
    encoded = escape(json.dumps(payload, ensure_ascii=False), quote=True)
    legend = "".join(
        f'<span><i style="background:{item["color"]}"></i>{escape(item["label"])}</span>'
        for item in payload
    )
    return (
        '<div class="chart" data-series="'
        f'{encoded}"><div class="chart-legend">{legend}</div><canvas aria-label="{escape(label)}净值曲线"></canvas>'
        '<div class="chart-tooltip" hidden></div></div>'
    )


NAV_PATHS = {
    "home.html": "/",
    "strategies.html": "/strategies",
    "strategy-current-taa.html": "/strategies",
    "strategy-p2-style-drawdown.html": "/strategies",
    "allocation.html": "/allocation",
    "research.html": "/research",
    "shadow.html": "/shadow",
    "data.html": "/data",
    "site-map.html": "/site-map",
}


def _navigation_context(current_path: str = "") -> dict[str, str]:
    return {
        f"nav_{path.strip('/').replace('-', '_') or 'home'}": "active" if path == current_path else ""
        for path in NAV_PATHS.values()
    }


def _render_page(
    template_name: str,
    reports: dict[str, dict[str, Any]] | None = None,
    data_as_of: str = "不可用",
    **context: str,
) -> str:
    page = _read_template(template_name).safe_substitute(context)
    current_path = NAV_PATHS[template_name]
    nav_context = _navigation_context(current_path)
    if reports is not None:
        data_as_of = _text(reports["manifest"].get("data_as_of"))
    return _read_template("base.html").safe_substitute(
        title=context.get("title", "CURRENT_TAA"),
        content=page,
        data_as_of=data_as_of,
        **nav_context,
    )


def _condition_label(passed: bool) -> str:
    css_class = "pass" if passed else "fail"
    label = "通过" if passed else "未通过"
    return f'<span class="result {css_class}">{label}</span>'




def _home(reports: dict[str, dict[str, Any]]) -> str:
    allocation = reports["allocation"]
    shadow = reports["shadow"]
    etf_rows = "".join(
        '<tr><td><strong>{}</strong><small>{}</small></td><td>{}{}</td></tr>'.format(
            _text(item.get("etf_name")),
            _text(item.get("etf_id")),
            _weight_bar(item.get("weight")),
            _pct(item.get("weight")),
        )
        for item in allocation.get("etf_target_weights", [])
    )
    metrics = "".join(
        (
            _metric("数据截至", _text(allocation.get("data_as_of"))),
            _metric("最新信号", _text(allocation.get("decision_date")), f"{_text(allocation.get('effective_date'))} 生效"),
            _metric("当前现金", _pct(allocation.get("cash_weight")), "未配置权重保留为现金"),
            _metric("Shadow 状态", "跟踪中" if shadow.get("status") == "tracking" else _text(shadow.get("status")), f"{_text(shadow.get('start_date'))} 起"),
        )
    )
    try:
        load_p2_strategy()
        p2_status = "REJECTED / CLOSED"
        p2_state = "rejected"
    except StrategyResultUnavailable:
        p2_status = "结果文件不可用"
        p2_state = "unavailable"
    return _render_page(
        "home.html", reports, title="CURRENT_TAA 首页", metrics=metrics,
        etf_rows=etf_rows or '<tr><td colspan="2">当前无 ETF 配置</td></tr>',
        p2_status=p2_status, p2_state=p2_state,
    )


def _allocation(reports: dict[str, dict[str, Any]]) -> str:
    report = reports["allocation"]
    index_rows = "".join(
        '<tr><td><strong>{}</strong><small>{}</small></td><td>{}{}</td></tr>'.format(
            _text(item.get("name")), _text(item.get("asset_id")), _weight_bar(item.get("weight")), _pct(item.get("weight"))
        )
        for item in report.get("index_target_weights", [])
    )
    etf_rows = "".join(
        '<tr><td><strong>{}</strong><small>{}</small></td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            _text(item.get("etf_name")),
            _text(item.get("etf_id")),
            _pct(item.get("weight")),
            _text(item.get("mapping_quality")),
            _text("；".join(item.get("notes", [])), "无补充说明"),
        )
        for item in report.get("etf_target_weights", [])
    )
    reasons = report.get("cash_reasons", [])
    cash_notes = "".join(f"<li>{_text(reason)}</li>" for reason in reasons) or "<li>当前没有因映射或价格缺失而额外转入现金。</li>"
    return _render_page(
        "allocation.html", reports, title="当前配置", decision_date=_text(report.get("decision_date")),
        effective_date=_text(report.get("effective_date")), cash_weight=_pct(report.get("cash_weight")),
        cash_metric=_metric("当前现金", _pct(report.get("cash_weight")), "未配置或当前不可用权重转入现金"),
        index_rows=index_rows, etf_rows=etf_rows, cash_notes=cash_notes,
    )


def _research(reports: dict[str, dict[str, Any]]) -> str:
    report = reports["research"]
    metrics = report.get("metrics", {})
    factors = report.get("factor_definition", {})
    latest = report.get("monthly_allocations", [])[-1] if report.get("monthly_allocations") else {}
    asset_names = {item.get("asset_id"): item.get("name") for item in report.get("assets", [])}
    signal_rows = "".join(
        '<tr><td><strong>{}</strong><small>{}</small></td><td>{}</td></tr>'.format(
            _text("现金" if asset_id == "CASH" else asset_names.get(asset_id)), _text(asset_id), _pct(weight)
        )
        for asset_id, weight in latest.get("weights", {}).items()
    )
    monthly_rows = "".join(
        '<tr><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            _text(item.get("signal_date")), _text(item.get("effective_date")),
            _text("、".join(f"{asset_names.get(k, '现金')} { _pct(v)}" for k, v in item.get("weights", {}).items()))
        )
        for item in reversed(report.get("monthly_allocations", [])[-12:])
    )
    summary = "".join((
        _metric("年化收益", _pct(metrics.get("annual_return")), "全收益指数研究口径"),
        _metric("最大回撤", _pct(metrics.get("max_drawdown")), "历史最大峰谷跌幅"),
        _metric("Sharpe", _num(metrics.get("sharpe")), "收益与波动的历史比值"),
    ))
    factor_cards = "".join((
        _metric("6 个月动量", _pct(factors.get("momentum_6m")), "观察中期趋势"),
        _metric("12 个月动量", _pct(factors.get("momentum_12m")), "观察长期趋势"),
        _metric("12 个月回撤韧性", _pct(factors.get("drawdown_resilience_12m")), "偏好回撤控制更稳的资产"),
    ))
    period = report.get("period", {})
    return _render_page(
        "research.html", reports, title="指数研究", summary=summary, factor_cards=factor_cards,
        period_start=_text(period.get("start")), period_end=_text(period.get("end")),
        signal_date=_text(latest.get("signal_date")), effective_date=_text(latest.get("effective_date")),
        signal_rows=signal_rows, monthly_rows=monthly_rows,
        chart=_chart(report.get("equity_curve", []), "CURRENT_TAA 全收益指数研究"),
        strategy_style_result=(
            '<section class="notice info">其他正式或失败策略请从 '
            '<a href="/strategies"><strong>策略中心</strong></a> 进入。</section>'
        ),
    )


def _shadow(reports: dict[str, dict[str, Any]]) -> str:
    report = reports["shadow"]
    benchmark = report.get("background_benchmark", {})
    metrics = report.get("metrics", {})
    summary = "".join((
        _metric("Shadow 年化", _pct(metrics.get("annual_return")), "启用日至今"),
        _metric("Shadow 最大回撤", _pct(metrics.get("max_drawdown")), "ETF 前复权口径"),
        _metric("Shadow Sharpe", _num(metrics.get("sharpe")), "短历史仅供跟踪"),
    ))
    names = {item.get("etf_id"): item.get("etf_name") for item in reports["allocation"].get("etf_target_weights", [])}
    names[benchmark.get("asset_id")] = benchmark.get("name")
    rows = "".join(
        '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            _text(item.get("signal_date")), _text(item.get("execution_date")), _text(item.get("reason")),
            _text("、".join(f"{names.get(k, '现金')} {k} {_pct(v)}" for k, v in item.get("weights", {}).items()))
        )
        for item in reversed(report.get("rebalance_records", []))
    ) or '<tr><td colspan="4">尚无调仓记录</td></tr>'
    disclosures = "".join(f"<li>{_text(item)}</li>" for item in report.get("disclosures", []))
    return _render_page(
        "shadow.html", reports, title="ETF Shadow 跟踪", summary=summary,
        start_date=_text(report.get("start_date")), end_date=_text(report.get("end_date")),
        benchmark_role=_text(benchmark.get("role")), rebalance_rows=rows, disclosures=disclosures,
        chart=_chart(report.get("equity_curve", []), "ETF Shadow", benchmark.get("equity_curve", [])),
    )


def _coverage_rows(items: list[dict[str, Any]], code_key: str) -> str:
    return "".join(
        '<tr><td><strong>{}</strong><small>{}</small></td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            _text(item.get("name")), _text(item.get(code_key)), _text(item.get("first_date")),
            _text(item.get("last_date")), _text(item.get("row_count"))
        )
        for item in items
    )


def _issue_list(items: list[Any], empty: str) -> str:
    if not items:
        return f'<li class="ok">{escape(empty)}</li>'
    return "".join(f"<li>{_text(item if isinstance(item, str) else json.dumps(item, ensure_ascii=False))}</li>" for item in items)


def _data(reports: dict[str, dict[str, Any]]) -> str:
    report = reports["data_status"]
    issues = "".join((
        _issue_list(report.get("missing_data", []), "未发现缺失数据"),
        _issue_list(report.get("duplicate_data", []), "未发现重复数据"),
        _issue_list(report.get("invalid_prices", []), "未发现非法价格"),
    ))
    return _render_page(
        "data.html", reports, title="数据状态", provider=_text(report.get("provider")),
        data_as_of=_text(report.get("data_as_of")), index_rows=_coverage_rows(report.get("research_index_coverage", []), "asset_id"),
        etf_rows=_coverage_rows(report.get("etf_coverage", []), "etf_id"), issues=issues,
    )


def _site_map(reports: dict[str, dict[str, Any]]) -> str:
    return _render_page("site-map.html", reports, title="网站地图")


def _strategy_center() -> str:
    try:
        current = load_current_strategy()
        current_state = "formal"
        current_status = "FORMAL / TRACKING"
        current_note = f"当前正式策略 · 数据截至 {_text(current['manifest'].get('data_as_of'))}"
        current_capability = "有"
        data_as_of = _text(current["manifest"].get("data_as_of"))
    except CurrentReportsUnavailable as exc:
        current_state = "unavailable"
        current_status = "结果文件不可用"
        current_note = _text(exc)
        current_capability = "不可核对"
        data_as_of = "不可用"
    try:
        p2 = load_p2_strategy()
        p2_state = "rejected"
        p2_status = "REJECTED / CLOSED"
        p2_note = f"DO_NOT_INTEGRATE · 数据截至 {_text(p2['manifest'].get('source_as_of_date'))}"
        p2_research = "有"
        p2_downstream = "无"
    except StrategyResultUnavailable as exc:
        p2_state = "unavailable"
        p2_status = "结果文件不可用"
        p2_note = _text(exc)
        p2_research = "不可核对"
        p2_downstream = "不可核对"
    return _render_page(
        "strategies.html", title="策略中心", data_as_of=data_as_of,
        current_state=current_state, current_status=current_status, current_note=current_note,
        current_capability=current_capability,
        p2_state=p2_state, p2_status=p2_status, p2_note=p2_note,
        p2_research=p2_research, p2_downstream=p2_downstream,
    )


def _current_strategy_page(reports: dict[str, dict[str, Any]]) -> str:
    research = reports["research"]
    allocation = reports["allocation"]
    shadow = reports["shadow"]
    factors = research.get("factor_definition", {})
    metrics = research.get("metrics", {})
    period = research.get("period", {})
    research_metrics = "".join((
        _metric("研究期间", f"{_text(period.get('start'))} 至 {_text(period.get('end'))}", "全收益指数口径"),
        _metric("年化收益", _pct(metrics.get("annual_return")), "历史研究结果"),
        _metric("最大回撤", _pct(metrics.get("max_drawdown")), "策略风险事实"),
        _metric("Sharpe", _num(metrics.get("sharpe")), "历史收益波动比"),
        _metric("研究资产", _text(research.get("asset_count")), "全收益指数资产数"),
    ))
    factor_metrics = "".join((
        _metric("6 个月动量", _pct(factors.get("momentum_6m")), "中期趋势"),
        _metric("12 个月动量", _pct(factors.get("momentum_12m")), "长期趋势"),
        _metric("12 个月回撤韧性", _pct(factors.get("drawdown_resilience_12m")), "回撤控制"),
    ))
    index_rows = "".join(
        '<tr><td><strong>{}</strong><small>{}</small></td><td>{}</td></tr>'.format(
            _text(item.get("name")), _text(item.get("asset_id")), _pct(item.get("weight"))
        )
        for item in allocation.get("index_target_weights", [])
    )
    etf_rows = "".join(
        '<tr><td><strong>{}</strong><small>{}</small></td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            _text(item.get("etf_name")), _text(item.get("etf_id")), _pct(item.get("weight")),
            _text(item.get("mapping_quality")), _text("；".join(item.get("notes", [])), "无补充说明"),
        )
        for item in allocation.get("etf_target_weights", [])
    )
    etf_names = {item.get("etf_id"): item.get("etf_name") for item in allocation.get("etf_target_weights", [])}
    rebalance_rows = "".join(
        '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            _text(item.get("signal_date")), _text(item.get("execution_date")), _text(item.get("reason")),
            _text("、".join(
                f"{'现金' if code == 'CASH' else etf_names.get(code, code)} {code} {_pct(weight)}"
                for code, weight in item.get("weights", {}).items()
            )),
        )
        for item in reversed(shadow.get("rebalance_records", []))
    ) or '<tr><td colspan="4">无调仓记录</td></tr>'
    shadow_metrics_data = shadow.get("metrics", {})
    shadow_metrics = "".join((
        _metric("Shadow 状态", _text(shadow.get("status")), f"{_text(shadow.get('start_date'))} 起"),
        _metric("跟踪截至", _text(shadow.get("end_date")), "ETF 前复权价格模拟"),
        _metric("年化收益", _pct(shadow_metrics_data.get("annual_return")), "短历史仅供跟踪"),
        _metric("最大回撤", _pct(shadow_metrics_data.get("max_drawdown")), "短历史仅供跟踪"),
        _metric("Sharpe", _num(shadow_metrics_data.get("sharpe")), "短历史仅供跟踪"),
    ))
    disclosures = "".join(f"<li>{_text(item)}</li>" for item in shadow.get("disclosures", []))
    benchmark = shadow.get("background_benchmark", {})
    return _render_page(
        "strategy-current-taa.html", reports, title="CURRENT_TAA 策略",
        shadow_status=_text(shadow.get("status")), factor_metrics=factor_metrics,
        research_metrics=research_metrics,
        research_chart=_chart(research.get("equity_curve", []), "CURRENT_TAA 全收益指数研究"),
        decision_date=_text(allocation.get("decision_date")), effective_date=_text(allocation.get("effective_date")),
        cash_weight=_pct(allocation.get("cash_weight")), index_rows=index_rows, etf_rows=etf_rows,
        rebalance_rows=rebalance_rows, shadow_metrics=shadow_metrics,
        shadow_chart=_chart(shadow.get("equity_curve", []), "ETF Shadow", benchmark.get("equity_curve", [])),
        disclosures=disclosures,
    )


def _p2_profile_rows(summary: dict[str, Any]) -> str:
    return "".join(
        '<tr><td><strong>{}</strong></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td>'
        '<td>{} / 4</td><td>{} / 8</td><td>{}</td><td><strong>{}</strong></td></tr>'.format(
            _text(profile.get("profile_id")), _condition_label(bool(profile.get("condition_a_passed"))),
            _condition_label(bool(profile.get("condition_b_passed"))),
            _condition_label(bool(profile.get("condition_c_passed"))),
            _condition_label(bool(profile.get("condition_d_passed"))),
            _text(profile.get("h60_positive_style_count")), _text(profile.get("h60_positive_fold_count")),
            _pct(profile.get("condition_c_median")), _text(profile.get("profile_support_status")),
        )
        for profile in summary.get("profile_decisions", [])
    )


def _p2_h60_rows(summary: dict[str, Any]) -> str:
    h60 = [item for item in summary.get("profile_fold_horizon", []) if item.get("horizon") == "H60"]
    values = {
        (item.get("walk_forward_fold_id"), item.get("profile_id")): item
        for item in h60
    }
    folds = sorted({str(item.get("walk_forward_fold_id")) for item in h60})
    profile_ids = ("PROFILE_A", "PROFILE_B", "PROFILE_C")
    rows = []
    for fold in folds:
        cells = []
        for profile_id in profile_ids:
            item = values.get((fold, profile_id), {})
            cells.append(_pct(item.get("profile_fold_median_peer_relative_return")))
        rows.append(
            f'<tr><td><strong>{_text(fold.replace("WF_", ""))}</strong></td>'
            + "".join(f"<td>{cell}</td>" for cell in cells)
            + "</tr>"
        )
    return "".join(rows)


def _p2_strategy_page(reports: dict[str, dict[str, Any]]) -> str:
    manifest = reports["manifest"]
    summary = reports["walk_forward_summary"]
    invariants = manifest.get("invariants", {})
    process_metrics = "".join((
        _metric("研究风格", _text(invariants.get("style_count")), "成长、价值、红利、自由现金流"),
        _metric("参数 Profile", _text(invariants.get("profile_count")), "预注册后不再拟合"),
        _metric("事件数量", _text(invariants.get("event_count")), "独立研究事件"),
        _metric("正式年度", _text(invariants.get("formal_fold_count")), "2018–2025"),
        _metric("主要期限", "H60", "60 个共同交易日"),
        _metric("最低年度", _text(invariants.get("minimum_available_fold_count")), "支持条件要求"),
    ))
    return _render_page(
        "strategy-p2-style-drawdown.html", title="P2 风格回撤再平衡",
        data_as_of=_text(manifest.get("source_as_of_date")), process_metrics=process_metrics,
        profile_rows=_p2_profile_rows(summary), h60_rows=_p2_h60_rows(summary),
    )


def _strategy_unavailable(title: str, message: str) -> HTMLResponse:
    content = _read_template("base.html").safe_substitute(
        title=f"{title}不可用", data_as_of="不可用", **_navigation_context("/strategies"),
        content=(
            f'<main class="unavailable"><p class="eyebrow">{escape(title)}</p><h1>策略结果不可用</h1>'
            f'<div class="notice danger">{escape(message)}</div>'
            '<p>策略中心仍可查看其他策略状态，本页不会用旧结果替代缺失文件。</p></main>'
        ),
    )
    return HTMLResponse(content, status_code=503)


PAGE_BUILDERS: dict[str, Callable[[dict[str, dict[str, Any]]], str]] = {
    "/": _home,
    "/allocation": _allocation,
    "/research": _research,
    "/shadow": _shadow,
    "/data": _data,
    "/site-map": _site_map,
}
PUBLIC_PATHS = (*PAGE_BUILDERS, "/strategies", "/strategies/current-taa", "/strategies/p2-style-drawdown")


def render_current_page(path: str, report_dir: Path | None = None) -> HTMLResponse:
    try:
        reports = load_current_reports(report_dir)
        return HTMLResponse(PAGE_BUILDERS[path](reports))
    except CurrentReportsUnavailable as exc:
        content = _read_template("base.html").safe_substitute(
            title="CURRENT_TAA 当前不可用",
            data_as_of="不可用",
            content=(
                '<main class="unavailable"><p class="eyebrow">CURRENT_TAA</p>'
                '<h1>当前结果不可用</h1>'
                f'<div class="notice danger">{escape(str(exc))}</div>'
                '<p>请先运行 <code>python scripts/update_current.py</code>，确认数据更新成功后再查看。</p></main>'
            ),
            **_navigation_context(),
        )
        return HTMLResponse(content, status_code=503)


def render_current_strategy_page(report_dir: Path | None = None) -> HTMLResponse:
    try:
        return HTMLResponse(_current_strategy_page(load_current_strategy(report_dir)))
    except CurrentReportsUnavailable as exc:
        return _strategy_unavailable("CURRENT_TAA", str(exc))


def render_p2_strategy_page(artifact_dir: Path | None = None) -> HTMLResponse:
    try:
        return HTMLResponse(_p2_strategy_page(load_p2_strategy(artifact_dir)))
    except StrategyResultUnavailable as exc:
        return _strategy_unavailable("P2 风格回撤再平衡", str(exc))


@router.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return render_current_page("/")


@router.get("/allocation", response_class=HTMLResponse)
def allocation() -> HTMLResponse:
    return render_current_page("/allocation")


@router.get("/research", response_class=HTMLResponse)
def research() -> HTMLResponse:
    return render_current_page("/research")


@router.get("/shadow", response_class=HTMLResponse)
def shadow() -> HTMLResponse:
    return render_current_page("/shadow")


@router.get("/data", response_class=HTMLResponse)
def data() -> HTMLResponse:
    return render_current_page("/data")


@router.get("/site-map", response_class=HTMLResponse)
def site_map() -> HTMLResponse:
    return render_current_page("/site-map")


@router.get("/strategies", response_class=HTMLResponse)
def strategies() -> HTMLResponse:
    return HTMLResponse(_strategy_center())


@router.get("/strategies/current-taa", response_class=HTMLResponse)
def current_taa_strategy() -> HTMLResponse:
    return render_current_strategy_page()


@router.get("/strategies/p2-style-drawdown", response_class=HTMLResponse)
def p2_style_drawdown_strategy() -> HTMLResponse:
    return render_p2_strategy_page()
