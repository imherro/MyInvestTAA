from backend.research_backtest_presentation import render_research_comparison_section


def test_research_comparison_section_has_three_named_curves_and_boundaries():
    html = render_research_comparison_section()

    assert "原13资产研究策略" in html
    assert "新增自由现金流后的14资产研究策略" in html
    assert "ETF执行净值（自实际可交易日起）" in html
    assert "480092.CNI" in html
    assert "国证自由现金流指数R" in html
    assert "ETF成立前没有使用指数收益填充" in html
    assert '<svg viewBox="0 0 920 350"' in html
