from engine.attribution import analyze_attribution
from engine.attribution.analyzer import _normalize_contribution
from engine.attribution.models import AttributionReport


def test_attribution_report_as_dict_contains_contribution():
    report = AttributionReport("S", {"drawdown": 100.0}, 1, "drawdown", [])

    assert report.as_dict()["contribution"]["drawdown"] == 100.0


def test_normalize_contribution_sums_to_one_hundred():
    contribution = _normalize_contribution({"drawdown": 1, "recovery": 1, "anchor": 1, "regime": 1, "allocation": 1})

    assert round(sum(contribution.values()), 2) == 100.0


def test_normalize_contribution_handles_zero_total():
    contribution = _normalize_contribution({"drawdown": 0, "recovery": 0, "anchor": 0, "regime": 0, "allocation": 0})

    assert all(value == 0.0 for value in contribution.values())


def test_analyze_attribution_returns_strategy():
    report = analyze_attribution()

    assert report["strategy"] == "MyInvestTAA"


def test_analyze_attribution_contributions_sum_to_one_hundred():
    report = analyze_attribution()

    assert round(sum(report["contribution"].values()), 2) == 100.0


def test_analyze_attribution_reports_observations():
    report = analyze_attribution()

    assert report["observations"] > 0


def test_analyze_attribution_reports_dominant_factor():
    report = analyze_attribution()

    assert report["dominant_factor"] in report["contribution"]


def test_analyze_attribution_handles_empty_states():
    report = analyze_attribution({"strategy": "Empty", "states": []})

    assert report["observations"] == 0
    assert sum(report["contribution"].values()) == 0.0


def test_analyze_attribution_uses_recorded_signals():
    report = analyze_attribution(
        {
            "strategy": "Unit",
            "states": [
                {
                    "weights": {"A": 100.0},
                    "selected_assets": ["A"],
                    "signals": {
                        "scores": [
                            {
                                "id": "A",
                                "drawdown_pressure": 80,
                                "recovery_score": 50,
                                "anchor_score": 70,
                            }
                        ],
                        "risk_budget": {"equity_limit": 80},
                        "turnover": 0.2,
                    },
                }
            ],
        }
    )

    assert report["contribution"]["drawdown"] > 0


def test_analyze_attribution_notes_are_present():
    report = analyze_attribution()

    assert report["notes"]
