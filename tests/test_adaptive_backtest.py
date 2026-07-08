from backtest.taa import run_taa_backtest


def _history(values: list[float]) -> list[dict]:
    return [
        {"date": f"2024-{index + 1:02d}-28", "close": value}
        for index, value in enumerate(values)
    ]


def test_run_taa_backtest_accepts_score_version_v8():
    result = run_taa_backtest(score_version="v8")

    assert result["assumptions"]["score_version"] == "v8"


def test_v8_scores_include_adaptive_weights():
    result = run_taa_backtest(score_version="v8")
    scores = next(state["signals"]["scores"] for state in result["states"] if state["signals"].get("scores"))

    assert "adaptive_factor_weights" in scores[0]


def test_v8_scores_include_adaptive_reason():
    result = run_taa_backtest(score_version="v8")
    scores = next(state["signals"]["scores"] for state in result["states"] if state["signals"].get("scores"))

    assert "adaptive_reason" in scores[0]


def test_v8_signals_record_adaptive_factor_weights():
    result = run_taa_backtest(score_version="v8")
    state = next(state for state in result["states"] if state["signals"].get("scores"))

    assert state["signals"]["adaptive_factor_weights"]


def test_v8_uses_stock_breadth_assets():
    result = run_taa_backtest(score_version="v8", stock_price_history={"688981.SH": _history([1, 2])})

    assert result["assumptions"]["stock_breadth_assets"] == 1


def test_v8_scores_include_stock_breadth_score():
    result = run_taa_backtest(score_version="v8", stock_price_history={"688981.SH": _history([1, 2])})
    scores = next(state["signals"]["scores"] for state in result["states"] if state["signals"].get("scores"))

    assert "stock_breadth_score" in scores[0]


def test_v8_records_adaptive_regime():
    result = run_taa_backtest(score_version="v8")
    scores = next(state["signals"]["scores"] for state in result["states"] if state["signals"].get("scores"))

    assert "adaptive_regime" in scores[0]


def test_v8_keeps_target_weights_when_smoothed():
    result = run_taa_backtest(score_version="v8", max_weight_step=10.0)

    assert any(state["signals"].get("target_weights") for state in result["states"][1:])


def test_v8_selected_assets_remain_etfs():
    result = run_taa_backtest(score_version="v8", stock_price_history={"688981.SH": _history([1, 2])})
    selected = {asset for state in result["states"] for asset in state.get("selected_assets", [])}

    assert "688981.SH" not in selected


def test_v8_metrics_are_available():
    result = run_taa_backtest(score_version="v8")

    assert {"annual_return", "max_drawdown", "sharpe"} <= set(result["metrics"])


def test_v8_assumptions_record_score_version():
    result = run_taa_backtest(score_version="v8")

    assert result["assumptions"]["score_version"] == "v8"


def test_v8_scores_have_selection_reasons():
    result = run_taa_backtest(score_version="v8")
    scores = next(state["signals"]["scores"] for state in result["states"] if state["signals"].get("scores"))

    assert scores[0]["selection_reason"]
