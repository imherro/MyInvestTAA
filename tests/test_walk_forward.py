import pytest

from backtest.walk_forward import DEFAULT_WALK_FORWARD_SPECS, run_walk_forward_validation


def _assets() -> list[dict]:
    return [
        {"id": "510300", "name": "HS300", "anchor_score": 60.0, "start_date": "2018-01-01"},
        {"id": "512760", "name": "Semi", "anchor_score": 55.0, "start_date": "2018-01-01"},
    ]


def _history(start: float, step: float) -> list[dict]:
    rows = []
    value = start
    for year in range(2018, 2026):
        for month in range(1, 13):
            value *= 1.0 + step
            rows.append({"date": f"{year}-{month:02d}-28", "close": round(value, 6)})
    return rows


def _histories() -> dict[str, list[dict]]:
    return {
        "510300": _history(1.0, 0.003),
        "512760": _history(1.0, 0.006),
    }


def _stock_histories() -> dict[str, list[dict]]:
    return {
        "688981.SH": _history(1.0, 0.008),
        "603501.SH": _history(1.0, 0.007),
    }


def test_walk_forward_returns_sections():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert {"benchmark", "rows", "versions", "best_version"} <= set(report)


def test_walk_forward_uses_default_specs():
    assert DEFAULT_WALK_FORWARD_SPECS[-1]["score_version"] == "v8"


def test_walk_forward_records_windows():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert report["windows"] > 0


def test_walk_forward_records_v7_summary():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert "V7_STOCK_BREADTH_SELECTION" in report["versions"]


def test_walk_forward_records_v8_summary():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert "V8_ADAPTIVE_SELECTION" in report["versions"]


def test_walk_forward_summary_has_win_rate():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert "win_rate" in report["versions"]["V7_STOCK_BREADTH_SELECTION"]


def test_walk_forward_rows_have_alpha():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert "alpha" in report["rows"][0]


def test_walk_forward_rows_have_train_and_test_dates():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert {"train_start", "test_start", "test_end"} <= set(report["rows"][0])


def test_walk_forward_accepts_custom_specs():
    report = run_walk_forward_validation(
        _assets(),
        _histories(),
        version_specs=[
            DEFAULT_WALK_FORWARD_SPECS[0],
            {"version": "V5_RELATIVE_STRENGTH_SELECTION", "score_version": "v5"},
        ],
    )

    assert set(report["versions"]) == {"V5_RELATIVE_STRENGTH_SELECTION"}


def test_walk_forward_passes_common_kwargs():
    report = run_walk_forward_validation(
        _assets(),
        _histories(),
        _stock_histories(),
        common_kwargs={"transaction_cost": 0.001},
    )

    assert report["rows"]


def test_walk_forward_rejects_invalid_train_years():
    with pytest.raises(ValueError):
        run_walk_forward_validation(_assets(), _histories(), train_years=0)


def test_walk_forward_rejects_invalid_test_years():
    with pytest.raises(ValueError):
        run_walk_forward_validation(_assets(), _histories(), test_years=0)


def test_walk_forward_handles_empty_histories():
    report = run_walk_forward_validation(_assets(), {})

    assert report["windows"] == 0


def test_walk_forward_reports_best_version():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert report["best_version"] in report["versions"]


def test_walk_forward_summary_has_drawdown_pass_rate():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert "drawdown_pass_rate" in report["versions"]["V7_STOCK_BREADTH_SELECTION"]


def test_walk_forward_rows_include_sharpe_and_calmar():
    report = run_walk_forward_validation(_assets(), _histories(), _stock_histories())

    assert {"sharpe", "calmar"} <= set(report["rows"][0])
