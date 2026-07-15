import json
import subprocess
import sys

from data_pipeline import build_strategy_diagnosis_report
from data_pipeline.strategy_diagnosis import _month_end_histories
from storage import MarketDataRepository, connect_database


ASSET_IDS = ["510300", "512890", "511010", "518880"]


def _report(report_path=None) -> dict:
    repository = MarketDataRepository(connect_database(":memory:"))
    return build_strategy_diagnosis_report(
        repository,
        provider_name="mock",
        start_date="2020-01-01",
        end_date="2026-07-08",
        asset_ids=ASSET_IDS,
        report_path=report_path,
    )


def test_strategy_diagnosis_report_returns_sections():
    report = _report()

    assert {"dataset", "diagnosis", "versions", "benchmark", "recommendations"} <= set(report)


def test_strategy_diagnosis_report_compares_strategy_versions():
    report = _report()

    assert {item["version"] for item in report["versions"]["rows"]} == {
        "V1_CURRENT",
        "V2_REGIME_SMOOTHING",
        "V3_TREND_RISK_ADJUSTED",
        "V4_REGIME_EXPOSURE_FLOOR",
        "V5_RELATIVE_STRENGTH_SELECTION",
        "V6_THEME_BREADTH_SELECTION",
        "V7_STOCK_BREADTH_SELECTION",
        "V8_ADAPTIVE_SELECTION",
        "V9_EXPOSURE_OPTIMIZED",
        "V10_ROBUST_EXPOSURE",
        "V11_PRODUCTION_FUSION",
    }


def test_strategy_diagnosis_report_records_best_version():
    report = _report()

    assert report["versions"]["best_version"] in {
        "V1_CURRENT",
        "V2_REGIME_SMOOTHING",
        "V3_TREND_RISK_ADJUSTED",
        "V4_REGIME_EXPOSURE_FLOOR",
        "V5_RELATIVE_STRENGTH_SELECTION",
        "V6_THEME_BREADTH_SELECTION",
        "V7_STOCK_BREADTH_SELECTION",
        "V8_ADAPTIVE_SELECTION",
        "V9_EXPOSURE_OPTIMIZED",
        "V10_ROBUST_EXPOSURE",
        "V11_PRODUCTION_FUSION",
    }


def test_strategy_diagnosis_report_records_regime_analysis():
    report = _report()

    assert "regimes" in report["diagnosis"]["regime_analysis"]


def test_strategy_diagnosis_report_records_decomposition():
    report = _report()

    assert "return_gap" in report["diagnosis"]["decomposition"]


def test_strategy_diagnosis_report_records_issue_summary():
    report = _report()

    assert isinstance(report["diagnosis"]["summary"], list)


def test_strategy_diagnosis_report_writes_json(tmp_path):
    path = tmp_path / "strategy_diagnosis_report.json"

    report = _report(report_path=path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["versions"]["best_version"] == report["versions"]["best_version"]


def test_strategy_diagnosis_report_records_static_benchmark():
    report = _report()

    assert report["benchmark"]["static"]["strategy_id"] == "SAA_60_40"


def test_strategy_diagnosis_report_records_recommendations():
    report = _report()

    assert report["recommendations"]


def test_strategy_diagnosis_report_records_benchmark_validation():
    report = _report()

    assert report["benchmark"]["validation"]["unit"] == "percent"


def test_strategy_diagnosis_report_records_attribution_v3():
    report = _report()

    assert {"allocation", "selection", "timing"} <= set(report["diagnosis"]["attribution_v3"])


def test_strategy_diagnosis_report_attribution_v3_uses_static_benchmark():
    report = _report()

    assert report["diagnosis"]["attribution_v3"]["benchmark"] == "SAA_60_40"


def test_strategy_diagnosis_report_records_regime_v3():
    report = _report()

    assert {"state", "confidence", "evidence"} <= set(report["diagnosis"]["regime_v3"])


def test_strategy_diagnosis_report_records_attribution_v5():
    report = _report()

    assert {"allocation", "selection", "timing"} <= set(report["diagnosis"]["attribution_v5"])


def test_strategy_diagnosis_report_records_attribution_v6():
    report = _report()

    assert {"allocation", "selection", "timing"} <= set(report["diagnosis"]["attribution_v6"])


def test_strategy_diagnosis_report_records_attribution_v7():
    report = _report()

    assert {"allocation", "selection", "timing"} <= set(report["diagnosis"]["attribution_v7"])


def test_strategy_diagnosis_report_records_attribution_v8():
    report = _report()

    assert {"allocation", "selection", "timing"} <= set(report["diagnosis"]["attribution_v8"])


def test_strategy_diagnosis_report_records_attribution_v9():
    report = _report()

    assert {"allocation", "selection", "timing"} <= set(report["diagnosis"]["attribution_v9"])


def test_strategy_diagnosis_report_records_attribution_v10():
    report = _report()

    assert {"allocation", "selection", "timing"} <= set(report["diagnosis"]["attribution_v10"])


def test_strategy_diagnosis_report_records_attribution_v11():
    report = _report()

    assert {"allocation", "selection", "timing"} <= set(report["diagnosis"]["attribution_v11"])


def test_strategy_diagnosis_report_records_selection_attribution():
    report = _report()

    assert {"old", "new", "improvement", "improved"} <= set(report["diagnosis"]["selection_attribution"]["selection"])


def test_strategy_diagnosis_report_records_selection_attribution_v2():
    report = _report()

    assert {"old", "new", "improvement", "improved"} <= set(report["diagnosis"]["selection_attribution_v2"]["selection"])


def test_strategy_diagnosis_report_records_selection_attribution_v3():
    report = _report()

    assert {"old", "new", "improvement", "improved"} <= set(report["diagnosis"]["selection_attribution_v3"]["selection"])


def test_strategy_diagnosis_report_records_adaptive_selection_attribution():
    report = _report()

    assert {"static_factor", "adaptive_factor", "selection"} <= set(report["diagnosis"]["adaptive_selection_attribution"])


def test_strategy_diagnosis_report_records_exposure_selection_attribution():
    report = _report()

    assert {"static_factor", "adaptive_factor", "selection"} <= set(report["diagnosis"]["exposure_selection_attribution"])


def test_strategy_diagnosis_report_records_robust_exposure_attribution():
    report = _report()

    assert {"static_factor", "adaptive_factor", "selection"} <= set(report["diagnosis"]["robust_exposure_attribution"])


def test_strategy_diagnosis_report_records_production_fusion_attribution():
    report = _report()

    assert {"static_factor", "adaptive_factor", "selection"} <= set(report["diagnosis"]["production_fusion_attribution"])


def test_strategy_diagnosis_report_records_selection_analysis():
    report = _report()

    assert {"version", "rows"} <= set(report["diagnosis"]["selection_analysis"])


def test_strategy_diagnosis_report_selection_analysis_rows_include_theme():
    report = _report()

    assert "theme" in report["diagnosis"]["selection_analysis"]["rows"][0]


def test_strategy_diagnosis_report_selection_analysis_rows_include_stock_breadth():
    report = _report()

    assert "stock_breadth_score" in report["diagnosis"]["selection_analysis"]["rows"][0]


def test_strategy_diagnosis_report_records_stock_breadth():
    report = _report()

    assert {"coverage", "rows", "source"} <= set(report["diagnosis"]["stock_breadth"])


def test_strategy_diagnosis_report_stock_breadth_records_coverage_ratio():
    report = _report()

    assert "coverage_ratio" in report["diagnosis"]["stock_breadth"]["coverage"]


def test_strategy_diagnosis_report_records_walk_forward():
    report = _report()

    assert {"windows", "versions", "rows"} <= set(report["diagnosis"]["walk_forward"])


def test_strategy_diagnosis_report_records_promotion():
    report = _report()

    assert {"benchmark", "rows", "best_candidate"} <= set(report["diagnosis"]["promotion"])


def test_strategy_diagnosis_report_records_adaptive_selection():
    report = _report()

    assert {"regime", "factor_weights", "rows"} <= set(report["diagnosis"]["adaptive_selection"])


def test_strategy_diagnosis_report_records_exposure_analysis():
    report = _report()

    assert {"version", "date", "current", "rows"} <= set(report["diagnosis"]["exposure_analysis"])


def test_strategy_diagnosis_report_exposure_current_has_reason():
    report = _report()

    assert "reason" in report["diagnosis"]["exposure_analysis"]["current"]


def test_strategy_diagnosis_report_records_strategy_selection():
    report = _report()

    assert {"winner", "confidence", "rows", "production_version"} <= set(report["diagnosis"]["strategy_selection"])


def test_strategy_diagnosis_report_strategy_selection_scores_v9():
    report = _report()

    assert any(row["version"] == "V9_EXPOSURE_OPTIMIZED" for row in report["diagnosis"]["strategy_selection"]["rows"])


def test_strategy_diagnosis_report_strategy_selection_scores_v10():
    report = _report()

    assert any(row["version"] == "V10_ROBUST_EXPOSURE" for row in report["diagnosis"]["strategy_selection"]["rows"])


def test_strategy_diagnosis_report_strategy_selection_scores_v11():
    report = _report()

    assert any(row["version"] == "V11_PRODUCTION_FUSION" for row in report["diagnosis"]["strategy_selection"]["rows"])


def test_strategy_diagnosis_report_records_robustness():
    report = _report()

    assert {"parameter_sensitivity", "bootstrap", "version_scores"} <= set(report["diagnosis"]["robustness"])


def test_strategy_diagnosis_report_records_stress():
    report = _report()

    assert {"scenarios", "rows", "versions"} <= set(report["diagnosis"]["stress"])


def test_strategy_diagnosis_report_records_final_strategy():
    report = _report()

    assert {"production_candidate", "candidate", "rows"} <= set(report["diagnosis"]["final_strategy"])


def test_strategy_diagnosis_report_records_production_readiness():
    report = _report()

    assert {"candidate", "status", "rows", "checks"} <= set(report["diagnosis"]["production_readiness"])


def test_strategy_diagnosis_report_records_strategy_registry():
    report = _report()

    assert {"production_candidate", "rows"} <= set(report["strategy_registry"])


def test_strategy_diagnosis_report_registry_marks_v3_candidate():
    report = _report()

    assert report["strategy_registry"]["production_candidate"] == "V3_TREND_RISK_ADJUSTED"


def test_strategy_diagnosis_report_registry_marks_v5_testing():
    report = _report()
    v5 = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V5_RELATIVE_STRENGTH_SELECTION")

    assert v5["status"] == "testing"


def test_strategy_diagnosis_report_registry_marks_v6_testing():
    report = _report()
    v6 = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V6_THEME_BREADTH_SELECTION")

    assert v6["status"] == "testing"


def test_strategy_diagnosis_report_registry_records_v6_evidence():
    report = _report()
    v6 = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V6_THEME_BREADTH_SELECTION")

    assert {"periods", "improvement"} <= set(v6["evidence"])


def test_strategy_diagnosis_report_registry_records_v7_evidence():
    report = _report()
    v7 = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V7_STOCK_BREADTH_SELECTION")

    assert {"periods", "improvement", "stock_breadth_coverage"} <= set(v7["evidence"])


def test_strategy_diagnosis_report_registry_records_v8_evidence():
    report = _report()
    v8 = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V8_ADAPTIVE_SELECTION")

    assert {"periods", "improvement", "stock_breadth_coverage"} <= set(v8["evidence"])


def test_strategy_diagnosis_report_registry_records_v9_evidence():
    report = _report()
    v9 = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V9_EXPOSURE_OPTIMIZED")

    assert {"periods", "improvement", "stock_breadth_coverage"} <= set(v9["evidence"])


def test_strategy_diagnosis_report_registry_records_v10_evidence():
    report = _report()
    v10 = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V10_ROBUST_EXPOSURE")

    assert {"periods", "improvement", "stock_breadth_coverage", "robustness_score"} <= set(v10["evidence"])


def test_strategy_diagnosis_report_registry_records_v11_evidence():
    report = _report()
    v11 = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V11_PRODUCTION_FUSION")

    assert {"periods", "improvement", "stock_breadth_coverage", "stress_score", "production_readiness"} <= set(v11["evidence"])


def test_strategy_diagnosis_report_registry_records_promotion_fields():
    report = _report()
    v7 = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V7_STOCK_BREADTH_SELECTION")

    assert {"promotion_score", "validation_windows", "approval_status"} <= set(v7)


def test_strategy_diagnosis_report_v4_records_equity_floor_assumption():
    report = _report()
    v4_row = next(row for row in report["versions"]["rows"] if row["version"] == "V4_REGIME_EXPOSURE_FLOOR")

    assert v4_row["assumptions"]["equity_floor_by_regime"]["bull"] == 70.0


def test_strategy_diagnosis_report_v5_records_score_version():
    report = _report()
    v5_row = next(row for row in report["versions"]["rows"] if row["version"] == "V5_RELATIVE_STRENGTH_SELECTION")

    assert v5_row["assumptions"]["score_version"] == "v5"


def test_strategy_diagnosis_report_v6_records_score_version():
    report = _report()
    v6_row = next(row for row in report["versions"]["rows"] if row["version"] == "V6_THEME_BREADTH_SELECTION")

    assert v6_row["assumptions"]["score_version"] == "v6"


def test_strategy_diagnosis_report_v7_records_score_version():
    report = _report()
    v7_row = next(row for row in report["versions"]["rows"] if row["version"] == "V7_STOCK_BREADTH_SELECTION")

    assert v7_row["assumptions"]["score_version"] == "v7"


def test_strategy_diagnosis_report_v8_records_score_version():
    report = _report()
    v8_row = next(row for row in report["versions"]["rows"] if row["version"] == "V8_ADAPTIVE_SELECTION")

    assert v8_row["assumptions"]["score_version"] == "v8"


def test_strategy_diagnosis_report_v9_records_score_version():
    report = _report()
    v9_row = next(row for row in report["versions"]["rows"] if row["version"] == "V9_EXPOSURE_OPTIMIZED")

    assert v9_row["assumptions"]["score_version"] == "v9"


def test_strategy_diagnosis_report_v10_records_score_version():
    report = _report()
    v10_row = next(row for row in report["versions"]["rows"] if row["version"] == "V10_ROBUST_EXPOSURE")

    assert v10_row["assumptions"]["score_version"] == "v10"


def test_strategy_diagnosis_report_v10_records_robust_exposure_config():
    report = _report()
    v10_row = next(row for row in report["versions"]["rows"] if row["version"] == "V10_ROBUST_EXPOSURE")

    assert "robust_exposure_config" in v10_row["assumptions"]


def test_strategy_diagnosis_report_v11_records_score_version():
    report = _report()
    v11_row = next(row for row in report["versions"]["rows"] if row["version"] == "V11_PRODUCTION_FUSION")

    assert v11_row["assumptions"]["score_version"] == "v11"


def test_strategy_diagnosis_report_v11_records_robust_exposure_config():
    report = _report()
    v11_row = next(row for row in report["versions"]["rows"] if row["version"] == "V11_PRODUCTION_FUSION")

    assert v11_row["assumptions"]["robust_exposure_config"]["target_volatility"] == 15.0


def test_strategy_diagnosis_report_benchmark_validation_passes_for_mock():
    report = _report()

    assert report["benchmark"]["validation"]["weight_check"] is True


def test_strategy_diagnosis_report_dataset_records_frequency():
    report = _report()

    assert report["dataset"]["frequency"] == "month_end"


def test_month_end_histories_keeps_last_row_per_month():
    histories = {
        "A": [
            {"date": "2024-01-02", "close": 1.0},
            {"date": "2024-01-31", "close": 1.1},
            {"date": "2024-02-01", "close": 1.2},
        ]
    }

    result = _month_end_histories(histories)

    assert [row["date"] for row in result["A"]] == ["2024-01-31", "2024-02-01"]
