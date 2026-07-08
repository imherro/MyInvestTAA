import pytest

from engine.governance import build_production_readiness_report


def _version_rows() -> list[dict]:
    return [
        {"version": "V6_THEME_BREADTH_SELECTION", "annual_return": 4.6, "max_drawdown": -12.1, "sharpe": 0.59, "calmar": 0.38},
        {"version": "V7_STOCK_BREADTH_SELECTION", "annual_return": 4.4, "max_drawdown": -12.8, "sharpe": 0.57, "calmar": 0.34},
        {"version": "V10_ROBUST_EXPOSURE", "annual_return": 3.6, "max_drawdown": -10.8, "sharpe": 0.52, "calmar": 0.33},
        {"version": "V11_PRODUCTION_FUSION", "annual_return": 4.3, "max_drawdown": -10.2, "sharpe": 0.61, "calmar": 0.42},
    ]


def _walk_forward() -> dict:
    return {
        "versions": {
            "V6_THEME_BREADTH_SELECTION": {"win_rate": 0.375, "min_alpha": -2.5},
            "V7_STOCK_BREADTH_SELECTION": {"win_rate": 0.625, "min_alpha": -4.2},
            "V10_ROBUST_EXPOSURE": {"win_rate": 0.5, "min_alpha": -4.3},
            "V11_PRODUCTION_FUSION": {"win_rate": 0.625, "min_alpha": -3.5},
        }
    }


def _stress() -> dict:
    return {
        "versions": {
            "V6_THEME_BREADTH_SELECTION": {"stress_no_failure": True, "stress_score": 55.0, "worst_drawdown": -12.0, "worst_return": -8.0},
            "V7_STOCK_BREADTH_SELECTION": {"stress_no_failure": True, "stress_score": 60.0, "worst_drawdown": -12.5, "worst_return": -7.0},
            "V10_ROBUST_EXPOSURE": {"stress_no_failure": True, "stress_score": 65.0, "worst_drawdown": -10.5, "worst_return": -6.0},
            "V11_PRODUCTION_FUSION": {"stress_no_failure": True, "stress_score": 85.0, "worst_drawdown": -9.0, "worst_return": -4.0},
        }
    }


def _robustness() -> dict:
    return {
        "version_scores": [
            {"version": "V6_THEME_BREADTH_SELECTION", "robustness_score": 50.0, "pass": True},
            {"version": "V7_STOCK_BREADTH_SELECTION", "robustness_score": 55.0, "pass": True},
            {"version": "V10_ROBUST_EXPOSURE", "robustness_score": 60.0, "pass": True},
            {"version": "V11_PRODUCTION_FUSION", "robustness_score": 70.0, "pass": True},
        ]
    }


def test_production_readiness_returns_candidate_and_status():
    report = build_production_readiness_report(_version_rows(), _walk_forward(), _stress(), _robustness())

    assert report["candidate"] == "V11_PRODUCTION_FUSION"
    assert report["status"] == "ready"


def test_production_readiness_returns_confidence():
    report = build_production_readiness_report(_version_rows(), _walk_forward(), _stress(), _robustness())

    assert report["confidence"] == round(report["rows"][0]["production_score_v3"] / 100.0, 4)


def test_production_readiness_rows_are_sorted():
    report = build_production_readiness_report(_version_rows(), _walk_forward(), _stress(), _robustness())
    scores = [row["production_score_v3"] for row in report["rows"]]

    assert scores == sorted(scores, reverse=True)


def test_production_readiness_row_contains_required_fields():
    report = build_production_readiness_report(_version_rows(), _walk_forward(), _stress(), _robustness())

    assert {"version", "production_score_v3", "stress_score", "checks", "ready"} <= set(report["rows"][0])


@pytest.mark.parametrize(
    ("mutator", "failed_check"),
    [
        (lambda rows, wf, stress, robust: rows[3].update({"sharpe": 0.49}), "absolute_performance"),
        (lambda rows, wf, stress, robust: wf["versions"]["V11_PRODUCTION_FUSION"].update({"win_rate": 0.5}), "walk_forward_win_rate"),
        (lambda rows, wf, stress, robust: wf["versions"]["V11_PRODUCTION_FUSION"].update({"min_alpha": -5.1}), "worst_window"),
        (lambda rows, wf, stress, robust: stress["versions"]["V11_PRODUCTION_FUSION"].update({"stress_no_failure": False}), "stress_no_failure"),
        (lambda rows, wf, stress, robust: robust["version_scores"][3].update({"pass": False}), "robustness_pass"),
    ],
)
def test_production_readiness_checks_can_fail(mutator, failed_check):
    rows = _version_rows()
    wf = _walk_forward()
    stress = _stress()
    robust = _robustness()
    mutator(rows, wf, stress, robust)

    report = build_production_readiness_report(
        rows,
        wf,
        stress,
        robust,
        candidate_versions=["V11_PRODUCTION_FUSION"],
    )

    assert report["status"] == "not_ready"
    assert report["checks"][failed_check] is False


def test_production_readiness_handles_empty_rows():
    report = build_production_readiness_report([], {"versions": {}}, {"versions": {}}, {"version_scores": []})

    assert report["candidate"] is None
    assert report["status"] == "not_ready"
    assert report["rows"] == []


def test_production_readiness_uses_custom_candidate_versions():
    report = build_production_readiness_report(
        _version_rows(),
        _walk_forward(),
        _stress(),
        _robustness(),
        candidate_versions=["V7_STOCK_BREADTH_SELECTION"],
    )

    assert [row["version"] for row in report["rows"]] == ["V7_STOCK_BREADTH_SELECTION"]


def test_production_readiness_reason_reports_ready():
    report = build_production_readiness_report(_version_rows(), _walk_forward(), _stress(), _robustness())

    assert "passed Production Governance V3" in report["reason"][0]


def test_production_readiness_reason_reports_failed_checks():
    rows = _version_rows()
    rows[3]["sharpe"] = 0.1

    report = build_production_readiness_report(
        rows,
        _walk_forward(),
        _stress(),
        _robustness(),
        candidate_versions=["V11_PRODUCTION_FUSION"],
    )

    assert "Failed checks" in report["reason"][1]
