from __future__ import annotations

from datetime import date
from html import escape

from backtest.execution import load_execution_backtest_report
from backtest.research.universe_comparison import load_research_universe_comparison
from backend.web_presentation import asset_name_catalog


SERIES = (
    ("baseline", "原13资产研究策略", "#667085"),
    ("candidate", "新增自由现金流后的14资产研究策略", "#15803d"),
    ("execution", "ETF执行净值（自实际可交易日起）", "#175ea8"),
)


def render_research_comparison_section() -> str:
    comparison = load_research_universe_comparison()
    execution = load_execution_backtest_report()
    if not comparison.get("available"):
        return '<section><h2>净值曲线对照</h2><p>尚未生成研究资产池对照报告。</p></section>'

    curves = {
        "baseline": comparison["baseline"]["equity_curve"],
        "candidate": comparison["candidate"]["equity_curve"],
        "execution": execution.get("equity_curve", []) if execution.get("available") else [],
    }
    added_asset_id = str(comparison["added_asset_id"])
    added_name = asset_name_catalog().get(added_asset_id, added_asset_id)
    selection = comparison.get("selection_impact", {})
    deltas = comparison.get("metric_deltas", {})
    execution_start = execution.get("period", {}).get("start", "-")
    return f"""
    <section class="research-curve-section">
      <style>
        .research-curve-frame {{ border:1px solid #cbd5e1; background:#fff; padding:10px; overflow:hidden; }}
        .research-curve-frame svg {{ display:block; width:100%; min-height:260px; }}
        .research-curve-legend {{ display:flex; flex-wrap:wrap; gap:8px 18px; margin:10px 0; font-size:13px; }}
        .research-curve-legend span {{ display:inline-flex; align-items:center; gap:6px; }}
        .research-curve-swatch {{ width:18px; height:3px; display:inline-block; }}
        .research-curve-note {{ color:#475467; font-size:14px; }}
        @media (max-width:700px) {{ .research-curve-frame {{ padding:4px; }} .research-curve-frame svg {{ min-height:210px; }} }}
      </style>
      <h2>净值曲线对照</h2>
      <p>研究层使用全收益指数决定策略；ETF层只使用真实上市后的前复权行情验证执行。</p>
      <div class="research-curve-frame">{_curve_svg(curves)}</div>
      <div class="research-curve-legend">{_legend_html(curves)}</div>
      <p class="research-curve-note">蓝色执行曲线从 {escape(str(execution_start))} 开始并重新归一为 1.0000；ETF成立前没有使用指数收益填充。</p>
      <table>
        <thead><tr><th>检查项</th><th>结果</th></tr></thead>
        <tbody>
          <tr><td>新增研究资产</td><td>{escape(added_asset_id)} {escape(added_name)}</td></tr>
          <tr><td>研究共同区间</td><td>{escape(comparison['comparison_period']['start'])} 至 {escape(comparison['comparison_period']['end'])}</td></tr>
          <tr><td>年化收益变化</td><td>{_percentage_point(deltas.get('annual_return'))}</td></tr>
          <tr><td>最大回撤变化</td><td>{_percentage_point(deltas.get('max_drawdown'))}（正数表示回撤减轻）</td></tr>
          <tr><td>夏普变化</td><td>{_signed_number(deltas.get('sharpe'))}</td></tr>
          <tr><td>入选月份</td><td>{int(selection.get('selected_months', 0))} / {int(selection.get('total_candidate_months', 0))}，占 {float(selection.get('selected_month_ratio', 0.0)):.1%}</td></tr>
          <tr><td>入选时平均权重</td><td>{float(selection.get('average_weight_when_selected', 0.0)):.1%}</td></tr>
          <tr><td>最高权重</td><td>{float(selection.get('maximum_weight', 0.0)):.1%}</td></tr>
        </tbody>
      </table>
    </section>
    """


def _curve_svg(curves: dict[str, list[dict]]) -> str:
    populated = {key: rows for key, rows in curves.items() if rows}
    if not populated:
        return "<p>暂无净值数据。</p>"
    width, height = 920.0, 350.0
    left, right, top, bottom = 62.0, 18.0, 20.0, 44.0
    all_rows = [row for rows in populated.values() for row in rows]
    ordinals = [_date_ordinal(row["date"]) for row in all_rows]
    values = [float(row["value"]) for row in all_rows]
    min_day, max_day = min(ordinals), max(ordinals)
    low, high = min(values), max(values)
    padding = max((high - low) * 0.08, 0.02)
    low, high = max(0.0, low - padding), high + padding

    def x(value: str) -> float:
        span = max(max_day - min_day, 1)
        return left + (_date_ordinal(value) - min_day) / span * (width - left - right)

    def y(value: float) -> float:
        span = max(high - low, 1e-9)
        return top + (high - value) / span * (height - top - bottom)

    grid = []
    for index in range(5):
        value = low + (high - low) * index / 4
        y_pos = y(value)
        grid.append(
            f'<line x1="{left:.1f}" y1="{y_pos:.1f}" x2="{width-right:.1f}" y2="{y_pos:.1f}" stroke="#e2e8f0"/>'
            f'<text x="{left-8:.1f}" y="{y_pos+4:.1f}" text-anchor="end" font-size="12" fill="#64748b">{value:.2f}</text>'
        )
    paths = []
    for key, _, color in SERIES:
        rows = populated.get(key, [])
        if not rows:
            continue
        points = " ".join(f"{x(row['date']):.1f},{y(float(row['value'])):.1f}" for row in rows)
        paths.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.4" vector-effect="non-scaling-stroke"/>')
    start_date = min(row["date"] for row in all_rows)
    end_date = max(row["date"] for row in all_rows)
    return (
        f'<svg viewBox="0 0 {int(width)} {int(height)}" role="img" aria-label="原研究策略、新增自由现金流策略和ETF执行净值曲线">'
        + "".join(grid)
        + "".join(paths)
        + f'<text x="{left:.1f}" y="{height-14:.1f}" font-size="12" fill="#64748b">{escape(start_date)}</text>'
        + f'<text x="{width-right:.1f}" y="{height-14:.1f}" text-anchor="end" font-size="12" fill="#64748b">{escape(end_date)}</text>'
        + "</svg>"
    )


def _legend_html(curves: dict[str, list[dict]]) -> str:
    return "".join(
        f'<span><i class="research-curve-swatch" style="background:{color}"></i>{escape(label)}</span>'
        for key, label, color in SERIES
        if curves.get(key)
    )


def _date_ordinal(value: str) -> int:
    return date.fromisoformat(value).toordinal()


def _percentage_point(value) -> str:
    return f"{float(value or 0.0):+.2%}"


def _signed_number(value) -> str:
    return f"{float(value or 0.0):+.3f}"
