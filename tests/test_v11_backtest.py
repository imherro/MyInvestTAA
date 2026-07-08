import pytest

from backtest.taa import run_taa_backtest


def _history(values: list[float]) -> list[dict]:
    return [
        {"date": f"2024-{index + 1:02d}-28", "close": value}
        for index, value in enumerate(values)
    ]


def _assets() -> list[dict]:
    return [
        {"id": "510300", "name": "HS300", "anchor_score": 60.0, "start_date": "2024-01-01"},
        {"id": "512760", "name": "Semi", "anchor_score": 55.0, "start_date": "2024-01-01"},
    ]


def _price_history() -> dict[str, list[dict]]:
    return {
        "510300": _history([1.0, 1.02, 1.03, 1.04, 1.03, 1.05]),
        "512760": _history([1.0, 1.03, 1.07, 1.10, 1.08, 1.12]),
    }


def _stock_history() -> dict[str, list[dict]]:
    return {
        "688981.SH": _history([1.0, 1.04, 1.08, 1.11, 1.10, 1.13]),
        "603501.SH": _history([1.0, 1.02, 1.05, 1.07, 1.06, 1.09]),
    }


def _first_v11_state(result: dict) -> dict:
    return next(state for state in result["states"] if state["signals"].get("exposure_decision"))


def test_run_taa_backtest_accepts_score_version_v11():
    result = run_taa_backtest(score_version="v11")

    assert result["assumptions"]["score_version"] == "v11"


def test_v11_records_robust_exposure_config():
    result = run_taa_backtest(score_version="v11", robust_exposure_config={"target_volatility": 15.0})

    assert result["assumptions"]["robust_exposure_config"] == {"target_volatility": 15.0}


def test_v11_records_exposure_v2_payload():
    result = run_taa_backtest(score_version="v11")
    decision = _first_v11_state(result)["signals"]["exposure_decision"]

    assert {"volatility_control", "drawdown_control", "raw_equity_target", "monthly_max_change"} <= set(decision)


def test_v11_risk_budget_uses_exposure_target():
    result = run_taa_backtest(score_version="v11")
    state = _first_v11_state(result)

    assert state["signals"]["risk_budget"]["equity_limit"] == state["signals"]["exposure_decision"]["equity_target"]


def test_v11_uses_stock_breadth_selection_without_adaptive_weights():
    result = run_taa_backtest(
        assets=_assets(),
        price_history=_price_history(),
        stock_price_history=_stock_history(),
        score_version="v11",
    )
    state = _first_v11_state(result)

    assert state["signals"]["adaptive_factor_weights"] == {}
    assert state["signals"]["scores"][0]["adaptive_regime"] == ""
    assert "stock_breadth_score" in state["signals"]["scores"][0]


def test_v11_selection_scores_match_v7_before_exposure():
    kwargs = {"assets": _assets(), "price_history": _price_history(), "stock_price_history": _stock_history()}
    v7 = run_taa_backtest(**kwargs, score_version="v7")
    v11 = run_taa_backtest(**kwargs, score_version="v11")

    v7_scores = v7["states"][1]["signals"]["scores"]
    v11_scores = v11["states"][1]["signals"]["scores"]
    assert [(row["id"], row["opportunity_score"]) for row in v11_scores] == [
        (row["id"], row["opportunity_score"]) for row in v7_scores
    ]


def test_v11_monthly_exposure_smoothing_limits_target_change():
    result = run_taa_backtest(score_version="v11", robust_exposure_config={"monthly_max_change": 5.0})
    targets = [
        state["signals"]["exposure_decision"]["equity_target"]
        for state in result["states"]
        if state["signals"].get("exposure_decision")
    ]

    assert all(abs(current - previous) <= 5.0 for previous, current in zip(targets, targets[1:]))


def test_v11_empty_result_records_robust_config():
    result = run_taa_backtest(
        assets=[],
        price_history={},
        score_version="v11",
        robust_exposure_config={"monthly_max_change": 5.0},
    )

    assert result["assumptions"]["robust_exposure_config"] == {"monthly_max_change": 5.0}


def test_run_taa_backtest_error_mentions_v11_for_unknown_score_version():
    with pytest.raises(ValueError, match="v11"):
        run_taa_backtest(score_version="bad")


@pytest.mark.parametrize("config_key", ["target_volatility", "moderate_drawdown", "deep_drawdown", "monthly_max_change"])
def test_v11_exposure_decision_keeps_configurable_controls(config_key):
    config = {
        "target_volatility": 15.0,
        "moderate_drawdown": -8.0,
        "deep_drawdown": -12.0,
        "monthly_max_change": 10.0,
    }
    result = run_taa_backtest(score_version="v11", robust_exposure_config=config)

    assert config_key in result["assumptions"]["robust_exposure_config"]
