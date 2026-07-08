import json
import subprocess
import sys


def test_run_full_validation_script_runs_with_mock(tmp_path):
    report_path = tmp_path / "full_validation_report.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_full_validation.py",
            "--provider",
            "mock",
            "--start",
            "2020-01-01",
            "--end",
            "2026-07-08",
            "--database",
            ":memory:",
            "--output",
            str(report_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["provider"] == "mock"
    assert report_path.exists()


def test_run_full_validation_script_outputs_experiment_id(tmp_path):
    report_path = tmp_path / "full_validation_report.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_full_validation.py",
            "--provider",
            "mock",
            "--database",
            ":memory:",
            "--output",
            str(report_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["experiment_id"]


def test_run_full_validation_script_accepts_return_type(tmp_path):
    report_path = tmp_path / "full_validation_report.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_full_validation.py",
            "--provider",
            "mock",
            "--database",
            ":memory:",
            "--output",
            str(report_path),
            "--return-type",
            "total_return",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["return_type"] == "total_return"
