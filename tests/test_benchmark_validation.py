from engine.benchmark_validation import validate_benchmark_report
from engine.benchmark_validation.validator import validate_benchmark_row


def test_validate_benchmark_row_accepts_valid_weights():
    row = {"strategy_id": "SAA", "weights": {"A": 60, "CASH": 40}, "annual_return": 1.0, "max_drawdown": -10.0}

    result = validate_benchmark_row(row)

    assert result["weight_check"] is True
    assert result["return_check"] is True


def test_validate_benchmark_row_flags_bad_weight_sum():
    row = {"strategy_id": "SAA", "weights": {"A": 80}, "annual_return": 1.0, "max_drawdown": -10.0}

    result = validate_benchmark_row(row)

    assert result["weight_check"] is False


def test_validate_benchmark_row_flags_suspicious_return():
    row = {"strategy_id": "SAA", "weights": {"A": 100}, "annual_return": 150.0, "max_drawdown": -10.0}

    result = validate_benchmark_row(row)

    assert result["return_check"] is False


def test_validate_benchmark_row_flags_bad_drawdown():
    row = {"strategy_id": "SAA", "weights": {"A": 100}, "annual_return": 1.0, "max_drawdown": 1.0}

    result = validate_benchmark_row(row)

    assert result["return_check"] is False


def test_validate_benchmark_report_returns_suite_summary():
    comparison = {
        "rows": [
            {"strategy_id": "MyInvestTAA", "weights": {}, "annual_return": 1.0, "max_drawdown": -10.0},
            {"strategy_id": "SAA", "weights": {"A": 60, "CASH": 40}, "annual_return": 1.0, "max_drawdown": -10.0},
        ]
    }

    result = validate_benchmark_report(comparison)

    assert result["strategy"] == "benchmark_suite"
    assert result["weight_check"] is True


def test_validate_benchmark_report_excludes_base_strategy():
    comparison = {"rows": [{"strategy_id": "MyInvestTAA", "weights": {}, "annual_return": 1.0, "max_drawdown": -10.0}]}

    result = validate_benchmark_report(comparison)

    assert result["rows"] == []


def test_validate_benchmark_report_declares_percent_unit():
    result = validate_benchmark_report({"rows": []})

    assert result["unit"] == "percent"


def test_validate_benchmark_report_collects_issues():
    comparison = {"rows": [{"strategy_id": "SAA", "weights": {"A": 80}, "annual_return": 150.0, "max_drawdown": -10.0}]}

    result = validate_benchmark_report(comparison)

    assert result["issues"]


def test_validate_benchmark_row_reports_weight_sum():
    row = {"strategy_id": "SAA", "weights": {"A": 55, "CASH": 45}, "annual_return": 1.0, "max_drawdown": -10.0}

    result = validate_benchmark_row(row)

    assert result["weight_sum"] == 100.0


def test_validate_benchmark_row_accepts_empty_weights_as_not_applicable():
    row = {"strategy_id": "SAA", "weights": {}, "annual_return": 1.0, "max_drawdown": -10.0}

    result = validate_benchmark_row(row)

    assert result["weight_check"] is True


def test_validate_benchmark_report_marks_failed_weight_check():
    comparison = {"rows": [{"strategy_id": "SAA", "weights": {"A": 75}, "annual_return": 1.0, "max_drawdown": -10.0}]}

    result = validate_benchmark_report(comparison)

    assert result["weight_check"] is False


def test_validate_benchmark_report_marks_failed_return_check():
    comparison = {"rows": [{"strategy_id": "SAA", "weights": {"A": 100}, "annual_return": 1.0, "max_drawdown": -120.0}]}

    result = validate_benchmark_report(comparison)

    assert result["return_check"] is False


def test_validate_benchmark_report_documents_cash_sleeve_assumption():
    result = validate_benchmark_report({"rows": []})

    assert any("cash_return" in note for note in result["notes"])
