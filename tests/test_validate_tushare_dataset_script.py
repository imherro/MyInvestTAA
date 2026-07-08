import json
import subprocess
import sys


def test_validate_tushare_dataset_script_runs_with_mock(tmp_path):
    db_path = tmp_path / "validated.sqlite"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_tushare_dataset.py",
            "--provider",
            "mock",
            "--assets",
            "510300",
            "512890",
            "511010",
            "518880",
            "--database",
            str(db_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["provider"] == "mock"
    assert payload["assets"] == 4


def test_validate_tushare_dataset_script_outputs_quality_score(tmp_path):
    db_path = tmp_path / "validated.sqlite"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_tushare_dataset.py",
            "--provider",
            "mock",
            "--assets",
            "510300",
            "512890",
            "511010",
            "518880",
            "--database",
            str(db_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["quality_score"] >= 50


def test_validate_tushare_dataset_script_outputs_dataset_id(tmp_path):
    db_path = tmp_path / "validated.sqlite"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_tushare_dataset.py",
            "--provider",
            "mock",
            "--assets",
            "510300",
            "512890",
            "511010",
            "518880",
            "--database",
            str(db_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["dataset_id"].endswith("_MOCK_CN_ETF")


def test_validate_tushare_dataset_script_outputs_performance_attribution(tmp_path):
    db_path = tmp_path / "validated.sqlite"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_tushare_dataset.py",
            "--provider",
            "mock",
            "--assets",
            "510300",
            "512890",
            "511010",
            "518880",
            "--database",
            str(db_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert "performance_attribution" in payload
