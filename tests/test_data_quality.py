from engine.data_quality import build_quality_summary, validate_price_history
from engine.data_quality.models import DataQualityReport


def test_data_quality_report_as_dict_contains_required_fields():
    report = DataQualityReport("A", 95, 3, 0, 0, 0, 0, [])

    payload = report.as_dict()

    assert {"asset_id", "score", "missing_days", "warnings"} <= set(payload)


def test_validate_price_history_scores_clean_data_high():
    report = validate_price_history(
        "A",
        [
            {"date": "2024-01-01", "close": 1.0},
            {"date": "2024-01-15", "close": 1.02},
        ],
    )

    assert report.score == 100.0


def test_validate_price_history_detects_duplicate_dates():
    report = validate_price_history(
        "A",
        [
            {"date": "2024-01-01", "close": 1.0},
            {"date": "2024-01-01", "close": 1.1},
        ],
    )

    assert report.duplicate_rows == 1


def test_validate_price_history_detects_non_positive_close():
    report = validate_price_history("A", [{"date": "2024-01-01", "close": 0}])

    assert report.invalid_prices == 1


def test_validate_price_history_detects_unsorted_dates():
    report = validate_price_history(
        "A",
        [
            {"date": "2024-02-01", "close": 1.0},
            {"date": "2024-01-01", "close": 1.0},
        ],
    )

    assert "dates are not sorted" in report.warnings


def test_validate_price_history_detects_missing_days():
    report = validate_price_history(
        "A",
        [
            {"date": "2024-01-01", "close": 1.0},
            {"date": "2024-02-10", "close": 1.0},
        ],
        max_gap_days=10,
    )

    assert report.missing_days == 30


def test_validate_price_history_detects_abnormal_jump():
    report = validate_price_history(
        "A",
        [
            {"date": "2024-01-01", "close": 1.0},
            {"date": "2024-01-02", "close": 2.0},
        ],
        jump_threshold=0.35,
    )

    assert report.abnormal_jumps == 1


def test_validate_price_history_empty_scores_zero():
    report = validate_price_history("A", [])

    assert report.score == 0.0


def test_build_quality_summary_returns_reports():
    summary = build_quality_summary(
        {"A": [{"date": "2024-01-01", "close": 1.0}]}
    )

    assert summary["asset_count"] == 1
    assert len(summary["reports"]) == 1


def test_build_quality_summary_counts_issues():
    summary = build_quality_summary(
        {"A": [{"date": "2024-01-01", "close": 0}]}
    )

    assert summary["issue_count"] == 1


def test_build_quality_summary_empty_histories():
    summary = build_quality_summary({})

    assert summary["average_score"] == 0.0
