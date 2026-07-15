from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from html import escape
import json
import math
from typing import Any

from backend.investment_chart import investment_chart_script
from release.orchestrator import load_release_json


ReleaseLoader = Callable[[str], dict[str, Any]]

RELEASE_ARTIFACTS = (
    "release_manifest.json",
    "system_acceptance_report.json",
    "current_market_decision.json",
    "execution_backtest_report.json",
)
UNAVAILABLE_MESSAGE = "当前正式投资指导不可用"


def build_investment_guidance(
    loader: ReleaseLoader = load_release_json,
) -> dict[str, Any]:
    try:
        manifest, acceptance, decision, execution = (
            loader(name) for name in RELEASE_ARTIFACTS
        )
        _validate_release(manifest, acceptance, decision, execution)
        allocation_records = _allocation_records(execution)
        allocation_chart = _allocation_chart(execution["monthly_allocations"])
        mapping = execution["mapping_summary"]
        gap_metrics = mapping["gap_metrics"]
        execution_decision = execution["decision"]

        return {
            "available": True,
            "source": "verified_committed_release",
            "release_id": manifest["release_id"],
            "decision_date": decision["decision_date"],
            "market_data_as_of": decision["market_data_as_of"],
            "production_actionable": False,
            "market_state": {
                key: deepcopy(decision["market_state"].get(key))
                for key in ("regime", "risk_level", "confidence")
            },
            "production_candidate": {
                key: deepcopy(decision["production_candidate"].get(key))
                for key in ("equity_weight", "cash_weight")
            },
            "strategy_equity": {
                "series_type": "execution_v1_equity_curve",
                "points": deepcopy(execution["equity_curve"]),
                "period": deepcopy(execution["period"]),
                "metrics": deepcopy(execution["metrics"]),
            },
            "benchmark": deepcopy(execution["benchmark"]),
            "allocation_chart": allocation_chart,
            "allocation_records": allocation_records,
            "recent_allocation_records": allocation_records[-12:],
            "execution_validation": {
                "ready": execution_decision["ready_for_execution_validation"],
                "reasons": deepcopy(execution_decision["reasons"]),
                "reason_details": deepcopy(execution_decision["reason_details"]),
                "tradable_weight_coverage": mapping["tradable_weight_coverage"],
                "tradable_weight_coverage_total_portfolio": mapping[
                    "tradable_weight_coverage_total_portfolio"
                ],
                "binary_any_gap_month_ratio": mapping[
                    "binary_any_gap_month_ratio"
                ],
                "average_gap_weight": gap_metrics["average_gap_weight"],
                "max_gap_weight": gap_metrics["max_gap_weight"],
                "gap_month_ratio_gt_5pct": gap_metrics[
                    "gap_month_ratio_gt_5pct"
                ],
                "gap_month_ratio_gt_10pct": gap_metrics[
                    "gap_month_ratio_gt_10pct"
                ],
                "gap_windows": deepcopy(mapping.get("gap_windows", {})),
            },
            "non_executable_assets": deepcopy(execution["non_executable_assets"]),
            "_decision_snapshot": deepcopy(decision),
        }
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "reason": UNAVAILABLE_MESSAGE,
            "production_actionable": False,
            "errors": [str(exc)],
        }


def render_investment_guidance(
    payload: dict[str, Any],
    *,
    product_css: str,
    primary_navigation: str,
) -> str:
    if payload.get("available") is not True:
        return _unavailable_page(
            product_css=product_css,
            primary_navigation=primary_navigation,
        )

    strategy = payload["strategy_equity"]
    metrics = strategy["metrics"]
    period = strategy["period"]
    points = strategy["points"]
    market = payload["market_state"]
    candidate = payload["production_candidate"]
    validation = payload["execution_validation"]
    records = payload["allocation_records"]
    recent = payload["recent_allocation_records"]
    benchmark = payload["benchmark"]

    recent_rows = "".join(_allocation_record_row(record) for record in recent)
    all_rows = "".join(_allocation_record_row(record) for record in records)
    reason_rows = "".join(
        f"<li>{escape(str(reason))}</li>" for reason in validation["reasons"]
    ) or "<li>无</li>"
    non_executable_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('research_asset_id', '')))}</td>"
        f"<td>{escape(str(item.get('mapping_quality', '')))}</td>"
        f"<td>{escape(str(item.get('reason', '')))}</td>"
        "</tr>"
        for item in payload["non_executable_assets"]
    ) or '<tr><td colspan="3">无</td></tr>'
    legend = "".join(
        '<span class="legend-item">'
        f'<span class="legend-swatch" style="background:{series["color"]}"></span>'
        f'{escape(series["asset_id"])}</span>'
        for series in payload["allocation_chart"]["series"]
    )

    return f"""<!doctype html>
<html lang="zh-CN" data-investment-guidance="true">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>当前配置决策</title>
  <style>{product_css}{_guidance_css()}</style>
</head>
<body>
  <header>
    <h1>当前配置决策</h1>
    <p>本页汇总最近一次经过来源校验的离线决策快照，用于人工判断。它不会生成订单，也不会自动替换 V11。</p>
    <p><span class="tag good">已验证快照</span><span class="tag warn">仅供人工审核</span><span class="tag blocked">非交易指令</span></p>
    {primary_navigation}
  </header>
  <main>
    <section class="hero">
      <span class="tag good">verified committed release</span>
      <h2>当前正式投资指导</h2>
      <div class="grid-3">
        {_metric_card("决策日期", payload["decision_date"])}
        {_metric_card("市场数据截至", payload["market_data_as_of"])}
        {_metric_card("市场状态", market["regime"])}
        {_metric_card("风险水平", market["risk_level"])}
        {_metric_card("判断置信度", _percent(market["confidence"]))}
        {_metric_card("Execution Validation", "已通过" if validation["ready"] else "尚未通过")}
      </div>
      <div class="allocation-summary">
        <div><strong>{_percent(candidate["equity_weight"])}</strong><span>V11 建议权益</span></div>
        <div><strong>{_percent(candidate["cash_weight"])}</strong><span>V11 建议现金</span></div>
      </div>
      <p class="alert-inline"><strong>边界：</strong>本系统只用于人工判断，不会生成订单、股数、金额或目标价格；所有内容均为非交易指令。Execution V1 仍是正式执行验证来源。</p>
    </section>

    <section>
      <h2>Execution V1 策略净值</h2>
      <p class="subtle">蓝线是 Execution V1；灰线是 510500.SH 南方中证500ETF 前复权基准。两者使用相同日期并从 1.0000 归一化，基准不参与策略计算。</p>
      <div class="chart-frame equity-chart" data-equity-chart>{_equity_svg(points, benchmark["points"])}<div class="chart-tooltip" data-chart-tooltip hidden></div></div>
      <script type="application/json" id="equity-chart-data">{_chart_json(points, benchmark["points"])}</script>
      <div class="grid-3 metric-grid">
        {_metric_card("周期", f'{period["start"]} 至 {period["end"]}')}
        {_metric_card("起始净值", _number(points[0]["value"]))}
        {_metric_card("期末净值", _number(points[-1]["value"]))}
        {_metric_card("年化收益", _percent(metrics["annual_return"]))}
        {_metric_card("最大回撤", _percent(metrics["max_drawdown"]))}
        {_metric_card("Sharpe", _number(metrics["sharpe"]))}
      </div>
      <div class="chart-legend"><span class="legend-item"><span class="legend-swatch strategy-swatch"></span>Execution V1</span><span class="legend-item"><span class="legend-swatch benchmark-swatch"></span>510500.SH 南方中证500ETF</span></div>
    </section>

    <section>
      <h2>Execution V1 映射后月度目标权重</h2>
      <p>这是映射后的月度<strong>目标配置</strong>，不是实际持仓。series_type=mapped_monthly_target_weights；actual_holding_series=false。</p>
      <div class="chart-frame">{_allocation_svg(payload["allocation_chart"])}</div>
      <div class="chart-legend" aria-label="目标权重图例">{legend}</div>
    </section>

    <section>
      <h2>Execution V1 月末目标配置快照</h2>
      <p>每月第一个交易日识别新月份，使用上月最后交易日数据计算目标，并从下一可执行交易日开始作用。本表是月度目标快照，不是成交记录，也不表示自然月最后一天一定开市。</p>
      <h3>最近 12 期</h3>
      <div class="table-wrap"><table><thead>{_allocation_table_head()}</thead><tbody>{recent_rows}</tbody></table></div>
      <details><summary>查看完整 {len(records)} 期历史</summary><div class="table-wrap"><table><thead>{_allocation_table_head()}</thead><tbody>{all_rows}</tbody></table></div></details>
    </section>

    <section class="{'hero' if validation['ready'] else 'alert'}">
      <h2>执行限制</h2>
      <div class="grid-3 metric-grid">
        {_metric_card("非现金研究权重覆盖率", _percent(validation["tradable_weight_coverage"]))}
        {_metric_card("全组合覆盖率", _percent(validation["tradable_weight_coverage_total_portfolio"]))}
        {_metric_card("任意缺口月份比例", _percent(validation["binary_any_gap_month_ratio"]))}
        {_metric_card("平均缺口", _percent(validation["average_gap_weight"]))}
        {_metric_card("最大缺口", _percent(validation["max_gap_weight"]))}
        {_metric_card("缺口 >5% / >10%", f'{_percent(validation["gap_month_ratio_gt_5pct"])} / {_percent(validation["gap_month_ratio_gt_10pct"])}')}
        {_metric_card("最近12个月缺口月份", _percent(validation["gap_windows"].get("recent_12_months", {}).get("binary_any_gap_month_ratio", 0)))}
        {_metric_card("连续无缺口起点", validation["gap_windows"].get("continuous_gap_free_suffix", {}).get("start") or "尚无")}
      </div>
      <h3>全局 Execution Validation 原因</h3><ul>{reason_rows}</ul>
      <h3>当前不可执行研究资产</h3>
      <div class="table-wrap"><table><thead><tr><th>研究资产</th><th>映射质量</th><th>正式原因</th></tr></thead><tbody>{non_executable_rows}</tbody></table></div>
      <p class="subtle">全历史 gate 仍包含 ETF 上市前月份；最近12个月缺口指标用于判断当前映射完整性，但不会覆盖或篡改全历史审计结果。</p>
    </section>

    {_legacy_audit_details(payload["_decision_snapshot"])}
  </main>
  <footer>Release {escape(str(payload["release_id"]))} · 用于人工判断 · 不会生成订单 · 非交易指令</footer>
  {investment_chart_script()}
</body>
</html>"""


def investment_guidance_api(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in payload.items()
        if not key.startswith("_")
    }


def _validate_release(
    manifest: dict[str, Any],
    acceptance: dict[str, Any],
    decision: dict[str, Any],
    execution: dict[str, Any],
) -> None:
    if manifest.get("available") is not True or manifest.get("verified") is not True:
        raise ValueError("verified committed release is unavailable")
    if (
        acceptance.get("available") is not True
        or acceptance.get("system_acceptance_passed") is not True
        or acceptance.get("blocking_errors")
    ):
        raise ValueError("system acceptance is unavailable")
    if decision.get("available") is not True or execution.get("available") is not True:
        raise ValueError("required committed artifact is unavailable")
    if acceptance.get("release_id") != manifest.get("release_id"):
        raise ValueError("release identity mismatch")
    if decision.get("production_actionable") is not False:
        raise ValueError("production boundary mismatch")

    required_decision = (
        "decision_date",
        "market_data_as_of",
        "market_state",
        "production_candidate",
        "execution_validation",
    )
    required_execution = (
        "equity_curve",
        "monthly_allocations",
        "source_research_allocations",
        "mapping_summary",
        "non_executable_assets",
        "decision",
        "period",
        "metrics",
        "benchmark",
    )
    for key in required_decision:
        if key not in decision:
            raise ValueError(f"current decision missing {key}")
    for key in required_execution:
        if key not in execution:
            raise ValueError(f"execution report missing {key}")

    points = execution["equity_curve"]
    if not isinstance(points, list) or not points:
        raise ValueError("execution equity curve is unavailable")
    for point in points:
        if not isinstance(point, dict) or set(point) != {"date", "value"}:
            raise ValueError("execution equity curve schema mismatch")
        _finite_number(point["value"])
    benchmark = execution["benchmark"]
    if benchmark.get("available") is not True or benchmark.get("asset_id") != "510500.SH":
        raise ValueError("510500 benchmark is unavailable")
    if benchmark.get("points") is None or len(benchmark["points"]) != len(points):
        raise ValueError("510500 benchmark does not align with execution curve")

    current_validation = decision["execution_validation"]
    execution_decision = execution["decision"]
    if (
        current_validation.get("ready")
        != execution_decision.get("ready_for_execution_validation")
        or current_validation.get("reasons") != execution_decision.get("reasons")
        or current_validation.get("reason_details")
        != execution_decision.get("reason_details")
    ):
        raise ValueError("execution validation status mismatch")


def _allocation_records(execution: dict[str, Any]) -> list[dict[str, Any]]:
    mapped = execution["monthly_allocations"]
    research = execution["source_research_allocations"]
    if not isinstance(mapped, list) or not mapped or not isinstance(research, list):
        raise ValueError("allocation history is unavailable")
    research_by_date = {row["date"]: row for row in research}
    mapped_dates = [row["date"] for row in mapped]
    if len(research_by_date) != len(research) or set(mapped_dates) != set(research_by_date):
        raise ValueError("allocation dates do not align")

    records: list[dict[str, Any]] = []
    execution_dates = [row["date"] for row in execution["equity_curve"]]
    for row in mapped:
        date = row["date"]
        weights = row["weights"]
        cash_breakdown = row["cash_breakdown"]
        if not isinstance(weights, dict) or not isinstance(cash_breakdown, dict):
            raise ValueError("allocation schema mismatch")
        for value in (*weights.values(), *cash_breakdown.values()):
            _finite_number(value)
        records.append(
            {
                "allocation_date": date,
                "signal_observation_date": date,
                "target_allocation_date": date,
                "next_execution_date": next(
                    (candidate for candidate in execution_dates if candidate > date),
                    None,
                ),
                "record_type": "monthly_target_snapshot",
                "research_target_weights": deepcopy(research_by_date[date]["weights"]),
                "mapped_target_weights": deepcopy(weights),
                "mapped_target_cash_weight": deepcopy(weights.get("CASH", 0.0)),
                "cash_breakdown": deepcopy(cash_breakdown),
            }
        )
    return records


def _allocation_chart(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dates = [row["date"] for row in rows]
    asset_ids = sorted(
        {asset_id for row in rows for asset_id in row["weights"]},
        key=lambda asset_id: (asset_id == "CASH", asset_id),
    )
    colors = (
        "#175ea8",
        "#116149",
        "#a35c00",
        "#7b4fa3",
        "#00838f",
        "#a32929",
        "#4f6d2f",
        "#9a4f70",
        "#6b7280",
    )
    series = [
        {
            "asset_id": asset_id,
            "values": [deepcopy(row["weights"].get(asset_id, 0.0)) for row in rows],
            "color": colors[index % len(colors)],
        }
        for index, asset_id in enumerate(asset_ids)
    ]
    return {
        "series_type": "mapped_monthly_target_weights",
        "actual_holding_series": False,
        "dates": dates,
        "series": series,
    }


def _equity_svg(points: list[dict[str, Any]], benchmark_points: list[dict[str, Any]]) -> str:
    width, height = 960.0, 280.0
    left, right, top, bottom = 58.0, 18.0, 18.0, 40.0
    values = [float(point["value"]) for point in points]
    benchmark_values = [float(point["value"]) for point in benchmark_points]
    low, high = min(values + benchmark_values), max(values + benchmark_values)
    span = high - low or 1.0
    plot_width = width - left - right
    plot_height = height - top - bottom
    denominator = max(len(points) - 1, 1)
    coordinates = [
        (
            left + plot_width * index / denominator,
            top + plot_height * (high - value) / span,
        )
        for index, value in enumerate(values)
    ]
    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
    benchmark_coordinates = [
        (
            left + plot_width * index / denominator,
            top + plot_height * (high - value) / span,
        )
        for index, value in enumerate(benchmark_values)
    ]
    benchmark_polyline = " ".join(
        f"{x:.2f},{y:.2f}" for x, y in benchmark_coordinates
    )
    return (
        f'<svg viewBox="0 0 {int(width)} {int(height)}" role="img" '
        'aria-label="Execution V1 策略净值图">'
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" class="axis"/>'
        f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" class="axis"/>'
        f'<polyline data-series="510500.SH" points="{benchmark_polyline}" class="benchmark-line"/>'
        f'<polyline data-series="execution-v1" points="{polyline}" class="equity-line"/>'
        f'<line data-crosshair x1="0" y1="{top}" x2="0" y2="{height-bottom}" class="crosshair" hidden/>'
        '<circle data-strategy-dot r="4" class="strategy-dot" hidden/>'
        '<circle data-benchmark-dot r="4" class="benchmark-dot" hidden/>'
        f'<text x="{left}" y="{height-12}" class="chart-label">{escape(str(points[0]["date"]))}</text>'
        f'<text x="{width-right}" y="{height-12}" text-anchor="end" '
        f'class="chart-label">{escape(str(points[-1]["date"]))}</text>'
        f'<text x="{left-8}" y="{top+5}" text-anchor="end" class="chart-label">{high:.2f}</text>'
        f'<text x="{left-8}" y="{height-bottom}" text-anchor="end" class="chart-label">{low:.2f}</text>'
        "</svg>"
    )


def _allocation_svg(chart: dict[str, Any]) -> str:
    width, height = 960.0, 320.0
    left, right, top, bottom = 58.0, 18.0, 18.0, 40.0
    dates = chart["dates"]
    series = chart["series"]
    plot_width = width - left - right
    plot_height = height - top - bottom
    denominator = max(len(dates) - 1, 1)
    cumulative = [0.0] * len(dates)
    polygons: list[str] = []
    for item in series:
        lower = list(cumulative)
        upper = [base + float(value) for base, value in zip(lower, item["values"])]
        cumulative = upper
        top_points = [
            (
                left + plot_width * index / denominator,
                top + plot_height * (1.0 - min(max(value, 0.0), 1.0)),
            )
            for index, value in enumerate(upper)
        ]
        lower_points = [
            (
                left + plot_width * index / denominator,
                top + plot_height * (1.0 - min(max(value, 0.0), 1.0)),
            )
            for index, value in reversed(list(enumerate(lower)))
        ]
        points = " ".join(
            f"{x:.2f},{y:.2f}" for x, y in (*top_points, *lower_points)
        )
        polygons.append(
            f'<polygon data-asset-id="{escape(item["asset_id"])}" points="{points}" '
            f'fill="{item["color"]}" fill-opacity="0.88"/>'
        )
    return (
        f'<svg viewBox="0 0 {int(width)} {int(height)}" role="img" '
        'aria-label="Execution V1 映射后月度目标权重图">'
        + "".join(polygons)
        + f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" class="axis"/>'
        + f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" class="axis"/>'
        + f'<text x="{left}" y="{height-12}" class="chart-label">{escape(str(dates[0]))}</text>'
        + f'<text x="{width-right}" y="{height-12}" text-anchor="end" '
        f'class="chart-label">{escape(str(dates[-1]))}</text>'
        + f'<text x="{left-8}" y="{top+5}" text-anchor="end" class="chart-label">100%</text>'
        + f'<text x="{left-8}" y="{height-bottom}" text-anchor="end" class="chart-label">0%</text>'
        + "</svg>"
    )


def _allocation_table_head() -> str:
    return (
        "<tr><th>月末观察/目标日</th><th>下一执行交易日</th><th>研究目标权重</th><th>映射后目标权重</th>"
        "<th>映射后现金</th><th>现金拆分</th></tr>"
    )


def _allocation_record_row(record: dict[str, Any]) -> str:
    return (
        "<tr>"
        f'<td>{escape(str(record["allocation_date"]))}</td>'
        f'<td>{escape(str(record["next_execution_date"] or "尚无"))}</td>'
        f'<td>{_weight_list(record["research_target_weights"])}</td>'
        f'<td>{_weight_list(record["mapped_target_weights"])}</td>'
        f'<td>{_percent(record["mapped_target_cash_weight"])}</td>'
        f'<td>{_weight_list(record["cash_breakdown"])}</td>'
        "</tr>"
    )


def _chart_json(points: list[dict[str, Any]], benchmark: list[dict[str, Any]]) -> str:
    return json.dumps(
        {"strategy": points, "benchmark": benchmark},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")


def _legacy_audit_details(decision: dict[str, Any]) -> str:
    production = decision.get("production_candidate", {})
    comparison = decision.get("comparison", {})
    summary = decision.get("decision_summary", {})
    sections = (
        (
            "Decision Date",
            {
                "decision_date": decision.get("decision_date"),
                "generated_at": decision.get("generated_at"),
            },
        ),
        (
            "Market Data Through",
            {"market_data_as_of": decision.get("market_data_as_of")},
        ),
        (
            "Governance State Date",
            {"governance_state_as_of": decision.get("governance_state_as_of")},
        ),
        ("Snapshot Mode", {"snapshot_mode": decision.get("snapshot_mode")}),
        ("Current Market State", decision.get("market_state", {})),
        ("Risk Level", decision.get("risk_summary", {})),
        ("V11 Production Candidate", production),
        (
            "V11 Metadata Available",
            {
                key: production.get(key)
                for key in (
                    "candidate_metadata_available",
                    "boundary_verified",
                    "unchanged",
                )
            },
        ),
        (
            "V11 Current Allocation Available",
            {
                "current_allocation_available": production.get(
                    "current_allocation_available"
                )
            },
        ),
        ("V11 Current Allocation", production.get("allocation", {})),
        (
            "V11 Equity and Cash",
            {key: production.get(key) for key in ("equity_weight", "cash_weight")},
        ),
        ("V11 Selected Assets", production.get("selected_assets", [])),
        (
            "Instrument Identifier Namespace",
            {"identifier_namespace": comparison.get("identifier_namespace")},
        ),
        (
            "Identifier Normalization Status",
            {
                key: comparison.get(key)
                for key in (
                    "identifier_normalization_verified",
                    "identifier_errors",
                )
            },
        ),
        ("Canonical V11 Weights", comparison.get("v11_canonical_weights", {})),
        (
            "Unresolved Instrument IDs",
            {
                key: comparison.get(key)
                for key in ("unresolved_v11_ids", "unresolved_shadow_ids")
            },
        ),
        ("V11 vs Shadow Weight Differences", comparison.get("weight_differences", {})),
        ("V11 Snapshot Integrity", production.get("allocation_integrity", {})),
        ("Research Allocation", decision.get("research_allocation", {})),
        ("Execution-Aware Shadow Allocation", decision.get("execution_shadow", {})),
        ("现金权重构成", {"cash_explanation": decision.get("cash_explanation")}),
        ("Execution Validation Status", decision.get("execution_validation", {})),
        ("Execution Gate Policy", decision.get("execution_validation", {}).get("gate_policy", {})),
        ("Current Constraints", decision.get("risk_summary", {}).get("key_risks", [])),
        ("Data Freshness", decision.get("data_freshness", {})),
        ("Required Source Status", decision.get("source_hash_verification", {})),
        ("Source Provenance", decision.get("source_manifest", {})),
        ("What Is Executable", summary.get("what_is_executable", [])),
        ("What Is Research-Only", summary.get("what_is_not_executable", [])),
        ("Blocking Conditions", summary.get("blocking_conditions", [])),
    )
    cards = "".join(
        f'<div class="card"><h3>{escape(title)}</h3>{_structured_table(value)}</div>'
        for title, value in sections
    )
    return (
        '<section><details><summary>查看既有决策审计字段</summary>'
        f'<div class="grid-2 audit-grid">{cards}</div>'
        '<div class="card"><h3>V11 vs Shadow Boundary</h3>'
        '<p>V11 remains unchanged. Research and Shadow are shown side by side only. '
        'No merged portfolio is created, and Shadow cannot replace V11.</p></div>'
        "</details></section>"
    )


def _structured_table(value: Any) -> str:
    if isinstance(value, dict):
        rows = value.items()
    elif isinstance(value, list):
        rows = ((str(index + 1), item) for index, item in enumerate(value))
    else:
        rows = (("value", value),)
    html_rows = "".join(
        f"<tr><th>{escape(str(key))}</th><td>{_format_value(item)}</td></tr>"
        for key, item in rows
    )
    return f'<div class="table-wrap"><table><tbody>{html_rows or "<tr><td>无</td></tr>"}</tbody></table></div>'


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return escape(str(value))


def _weight_list(weights: dict[str, Any]) -> str:
    return "<br/>".join(
        f"<strong>{escape(str(asset_id))}</strong> {_percent(value)}"
        for asset_id, value in sorted(weights.items())
    ) or "无"


def _metric_card(label: str, value: Any) -> str:
    return (
        '<div class="card metric-card">'
        f"<span>{escape(str(label))}</span><strong>{escape(str(value))}</strong>"
        "</div>"
    )


def _percent(value: Any) -> str:
    return f"{_finite_number(value):.1%}"


def _number(value: Any) -> str:
    return f"{_finite_number(value):.4f}"


def _finite_number(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite numeric value")
    return number


def _unavailable_page(*, product_css: str, primary_navigation: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN" data-investment-guidance="true">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>当前配置决策</title>
  <style>{product_css}{_guidance_css()}</style>
</head>
<body>
  <header>
    <h1>当前配置决策</h1>
    <p>用于人工判断。它不会生成订单，也不会自动替换 V11。</p>
    <p><span class="tag blocked">非交易指令</span></p>
    {primary_navigation}
  </header>
  <main><section class="alert">
    <h2>{UNAVAILABLE_MESSAGE}</h2>
    <p>Decision snapshot unavailable for user review. verified committed release 未通过完整性检查，因此不展示部分净值、配置或执行数据。</p>
  </section></main>
  <footer>不会生成订单 · 非交易指令</footer>
</body>
</html>"""


def _guidance_css() -> str:
    return """
      .allocation-summary { display:grid; grid-template-columns:repeat(2,minmax(0,220px)); gap:12px; margin:18px 0; }
      .allocation-summary div { border-left:4px solid var(--blue); padding:8px 12px; background:#f7fafc; }
      .allocation-summary strong { display:block; font-size:28px; }
      .allocation-summary span,.metric-card span { color:var(--muted); font-size:13px; }
      .metric-card strong { display:block; margin-top:5px; overflow-wrap:anywhere; }
      .alert-inline,.benchmark-unavailable { padding:12px; border:1px solid #d8bd7a; background:#fffaf0; }
      .benchmark-unavailable { margin-top:14px; }
      .chart-frame { width:100%; overflow:hidden; border:1px solid var(--line); background:#fff; }
      .chart-frame svg { display:block; width:100%; height:auto; min-height:210px; }
      .axis { stroke:#78838c; stroke-width:1; }
      .equity-line { fill:none; stroke:var(--blue); stroke-width:3; vector-effect:non-scaling-stroke; }
      .benchmark-line { fill:none; stroke:#8a949d; stroke-width:2; stroke-dasharray:7 5; vector-effect:non-scaling-stroke; }
      .equity-chart { position:relative; touch-action:none; }
      .crosshair { stroke:#303942; stroke-width:1; stroke-dasharray:3 3; vector-effect:non-scaling-stroke; }
      .strategy-dot { fill:var(--blue); stroke:#fff; stroke-width:2; }
      .benchmark-dot { fill:#69747d; stroke:#fff; stroke-width:2; }
      .chart-tooltip { position:absolute; top:12px; width:180px; transform:translateX(-50%); padding:9px 10px; border:1px solid #c7cfd6; background:rgba(255,255,255,.96); box-shadow:0 4px 12px rgba(0,0,0,.12); pointer-events:none; font-size:12px; }
      .chart-tooltip strong,.chart-tooltip span { display:block; }
      .chart-label { fill:#5b6874; font-size:12px; }
      .chart-legend { display:flex; flex-wrap:wrap; gap:7px 14px; margin-top:10px; }
      .legend-item { display:inline-flex; align-items:center; gap:5px; font-size:13px; }
      .legend-swatch { width:12px; height:12px; display:inline-block; }
      .strategy-swatch { background:var(--blue); }
      .benchmark-swatch { background:#8a949d; }
      .audit-grid { margin-top:14px; }
      .audit-grid td { overflow-wrap:anywhere; word-break:break-word; }
      @media (max-width:560px) {
        .allocation-summary { grid-template-columns:1fr; }
        .chart-frame svg { min-height:170px; }
        .metric-grid { grid-template-columns:1fr; }
      }
    """
