import json
from pathlib import Path

import pytest

from current_taa.pipeline import REPORT_NAMES, ROOT, run_current_pipeline


def test_pipeline_writes_exactly_five_current_reports(tmp_path):
    target = tmp_path / "current"
    run_current_pipeline(root=ROOT, shadow_start_date="2026-07-14", output_dir=target)
    assert {path.name for path in target.iterdir()} == REPORT_NAMES


def test_pipeline_output_is_deterministic(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_current_pipeline(root=ROOT, shadow_start_date="2026-07-14", output_dir=first)
    run_current_pipeline(root=ROOT, shadow_start_date="2026-07-14", output_dir=second)
    assert {name: (first / name).read_bytes() for name in REPORT_NAMES} == {name: (second / name).read_bytes() for name in REPORT_NAMES}


def test_subsequent_run_reuses_fixed_shadow_start_date(tmp_path):
    target = tmp_path / "current"
    run_current_pipeline(root=ROOT, shadow_start_date="2026-07-14", output_dir=target)
    reports = run_current_pipeline(root=ROOT, output_dir=target)
    assert reports["manifest.json"]["shadow_start_date"] == "2026-07-14"


def test_failure_replaces_old_current_with_failure_status_only(tmp_path):
    target = tmp_path / "current"
    run_current_pipeline(root=ROOT, shadow_start_date="2026-07-14", output_dir=target)
    broken_root = tmp_path / "broken"
    broken_root.mkdir()
    with pytest.raises(Exception):
        run_current_pipeline(root=broken_root, shadow_start_date="2026-07-14", output_dir=target)
    assert [path.name for path in target.iterdir()] == ["data_status.json"]
    assert json.loads((target / "data_status.json").read_text(encoding="utf-8"))["current"] is False


def test_new_pipeline_does_not_import_old_product_paths():
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "current_taa").glob("*.py"))
    for forbidden in ("release.", "decision.v11_current", "approval", "execution.v2", "counterfactual"):
        assert forbidden not in source


def test_manifest_contains_version_but_no_governance_state(tmp_path):
    target = tmp_path / "current"
    reports = run_current_pipeline(root=ROOT, shadow_start_date="2026-07-14", output_dir=target)
    manifest = reports["manifest.json"]
    assert manifest["implementation_version"]
    assert not ({"approval", "gate", "promotion", "protected_hash"} & set(manifest))


def test_shadow_start_resolution_failure_clears_old_success_reports(tmp_path):
    target = tmp_path / "current"
    run_current_pipeline(root=ROOT, shadow_start_date="2026-07-14", output_dir=target)
    (target / "manifest.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(Exception):
        run_current_pipeline(root=ROOT, output_dir=target)
    assert [path.name for path in target.iterdir()] == ["data_status.json"]
    failure = json.loads((target / "data_status.json").read_text(encoding="utf-8"))
    assert failure["current"] is False
