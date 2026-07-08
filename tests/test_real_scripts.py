import json
import subprocess
import sys


def test_build_research_dataset_script_writes_version(tmp_path):
    db_path = tmp_path / "research.sqlite"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_research_dataset.py",
            "--source",
            "mock",
            "--database",
            str(db_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["dataset_id"].endswith("_MOCK_CN_ETF")


def test_download_market_dataset_script_runs_with_mock(tmp_path):
    db_path = tmp_path / "download.sqlite"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/download_market_dataset.py",
            "--provider",
            "mock",
            "--assets",
            "510300",
            "--database",
            str(db_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["imported_assets"] == 1
