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
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
REPORT_NAMES = ("research", "allocation", "shadow", "data_status", "manifest")

router = APIRouter()


class CurrentReportsUnavailable(RuntimeError):
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


def _notice(message: str, tone: str = "info") -> str:
    return f'<div class="notice {tone}">{escape(message)}</div>'


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


def _render_page(template_name: str, reports: dict[str, dict[str, Any]], **context: str) -> str:
    page = _read_template(template_name).safe_substitute(context)
    manifest = reports["manifest"]
    return _read_template("base.html").safe_substitute(
        title=context.get("title", "CURRENT_TAA"),
        content=page,
        data_as_of=_text(manifest.get("data_as_of")),
    )


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
    return _render_page("home.html", reports, title="CURRENT_TAA 首页", metrics=metrics, etf_rows=etf_rows or '<tr><td colspan="2">当前无 ETF 配置</td></tr>')


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


PAGE_BUILDERS: dict[str, Callable[[dict[str, dict[str, Any]]], str]] = {
    "/": _home,
    "/allocation": _allocation,
    "/research": _research,
    "/shadow": _shadow,
    "/data": _data,
    "/site-map": _site_map,
}


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
        )
        return HTMLResponse(content, status_code=503)


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
