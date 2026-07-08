from data_pipeline import build_strategy_diagnosis_report
from storage import MarketDataRepository, connect_database


ASSET_IDS = ["510300", "512890", "511010", "518880"]


def _report() -> dict:
    repository = MarketDataRepository(connect_database(":memory:"))
    return build_strategy_diagnosis_report(
        repository,
        provider_name="mock",
        start_date="2020-01-01",
        end_date="2026-07-08",
        asset_ids=ASSET_IDS,
        report_path=None,
    )


def test_report_includes_v8_version():
    report = _report()

    assert any(row["version"] == "V8_ADAPTIVE_SELECTION" for row in report["versions"]["rows"])


def test_report_includes_v9_version():
    report = _report()

    assert any(row["version"] == "V9_EXPOSURE_OPTIMIZED" for row in report["versions"]["rows"])


def test_report_includes_v10_version():
    report = _report()

    assert any(row["version"] == "V10_ROBUST_EXPOSURE" for row in report["versions"]["rows"])


def test_report_records_attribution_v8():
    report = _report()

    assert "attribution_v8" in report["diagnosis"]


def test_report_records_attribution_v9():
    report = _report()

    assert "attribution_v9" in report["diagnosis"]


def test_report_records_attribution_v10():
    report = _report()

    assert "attribution_v10" in report["diagnosis"]


def test_report_records_adaptive_selection_attribution():
    report = _report()

    assert "adaptive_factor" in report["diagnosis"]["adaptive_selection_attribution"]


def test_report_records_exposure_selection_attribution():
    report = _report()

    assert "adaptive_factor" in report["diagnosis"]["exposure_selection_attribution"]


def test_report_records_robust_exposure_attribution():
    report = _report()

    assert "adaptive_factor" in report["diagnosis"]["robust_exposure_attribution"]


def test_report_records_adaptive_selection():
    report = _report()

    assert {"regime", "factor_weights", "rows"} <= set(report["diagnosis"]["adaptive_selection"])


def test_report_adaptive_selection_rows_include_reason():
    report = _report()

    assert "adaptive_reason" in report["diagnosis"]["adaptive_selection"]["rows"][0]


def test_report_selection_analysis_is_v11():
    report = _report()

    assert report["diagnosis"]["selection_analysis"]["version"] == "v11"


def test_report_walk_forward_includes_v8():
    report = _report()

    assert "V8_ADAPTIVE_SELECTION" in report["diagnosis"]["walk_forward"]["versions"]


def test_report_walk_forward_includes_v9():
    report = _report()

    assert "V9_EXPOSURE_OPTIMIZED" in report["diagnosis"]["walk_forward"]["versions"]


def test_report_walk_forward_includes_v10():
    report = _report()

    assert "V10_ROBUST_EXPOSURE" in report["diagnosis"]["walk_forward"]["versions"]


def test_report_promotion_includes_v8():
    report = _report()

    assert any(row["version"] == "V8_ADAPTIVE_SELECTION" for row in report["diagnosis"]["promotion"]["rows"])


def test_report_promotion_includes_v9():
    report = _report()

    assert any(row["version"] == "V9_EXPOSURE_OPTIMIZED" for row in report["diagnosis"]["promotion"]["rows"])


def test_report_promotion_includes_v10():
    report = _report()

    assert any(row["version"] == "V10_ROBUST_EXPOSURE" for row in report["diagnosis"]["promotion"]["rows"])


def test_report_registry_records_v8():
    report = _report()

    assert any(row["version"] == "V8_ADAPTIVE_SELECTION" for row in report["strategy_registry"]["rows"])


def test_report_registry_v8_has_promotion_fields():
    report = _report()
    row = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V8_ADAPTIVE_SELECTION")

    assert {"promotion_score", "validation_windows", "approval_status"} <= set(row)


def test_report_registry_v9_has_promotion_fields():
    report = _report()
    row = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V9_EXPOSURE_OPTIMIZED")

    assert {"promotion_score", "validation_windows", "approval_status"} <= set(row)


def test_report_registry_v10_has_promotion_fields():
    report = _report()
    row = next(row for row in report["strategy_registry"]["rows"] if row["version"] == "V10_ROBUST_EXPOSURE")

    assert {"promotion_score", "validation_windows", "approval_status"} <= set(row)


def test_report_recommendations_include_adaptive():
    report = _report()

    assert any("adaptive" in item.lower() for item in report["recommendations"])


def test_report_recommendations_include_exposure():
    report = _report()

    assert any("exposure" in item.lower() for item in report["recommendations"])


def test_report_adaptive_factor_weights_have_weights():
    report = _report()

    assert "weights" in report["diagnosis"]["adaptive_selection"]["factor_weights"]


def test_report_records_exposure_analysis():
    report = _report()

    assert {"current", "rows"} <= set(report["diagnosis"]["exposure_analysis"])


def test_report_records_strategy_selection():
    report = _report()

    assert {"winner", "confidence", "rows"} <= set(report["diagnosis"]["strategy_selection"])


def test_report_records_robustness():
    report = _report()

    assert {"parameter_sensitivity", "version_scores"} <= set(report["diagnosis"]["robustness"])


def test_report_records_final_strategy():
    report = _report()

    assert {"candidate", "rows"} <= set(report["diagnosis"]["final_strategy"])
