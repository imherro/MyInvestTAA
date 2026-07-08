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


def test_strategy_diagnosis_report_compares_three_versions():
    report = _report()

    assert {item["version"] for item in report["versions"]["rows"]} == {
        "V1_CURRENT",
        "V2_REGIME_SMOOTHING",
        "V3_TREND_RISK_ADJUSTED",
        "V4_REGIME_EXPOSURE_FLOOR",
    }


def test_strategy_diagnosis_report_records_best_version():
    report = _report()

    assert report["versions"]["best_version"] in {
        "V1_CURRENT",
        "V2_REGIME_SMOOTHING",
        "V3_TREND_RISK_ADJUSTED",
        "V4_REGIME_EXPOSURE_FLOOR",
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


def test_strategy_diagnosis_script_runs_with_mock(tmp_path):
    path = tmp_path / "strategy_diagnosis_report.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_strategy_diagnosis.py",
            "--provider",
            "mock",
            "--database",
            ":memory:",
            "--output",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["best_version"]
    assert path.exists()


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


def test_strategy_diagnosis_report_v4_records_equity_floor_assumption():
    report = _report()
    v4_row = next(row for row in report["versions"]["rows"] if row["version"] == "V4_REGIME_EXPOSURE_FLOOR")

    assert v4_row["assumptions"]["equity_floor_by_regime"]["bull"] == 70.0


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
