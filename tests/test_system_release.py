from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import shutil

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from decision.current_market.engine import _production_candidate
from decision.current_market.instrument_ids import load_execution_instrument_aliases
from decision.current_market.sources import load_current_market_sources
from release.build_graph import BUILD_STEPS, dependency_graph, dependency_graph_hash
from release.contracts import forbidden_field_paths, semantic_hash, sha256_file
from release.models import ReleaseBuildConfig
from release.orchestrator import (
    LOCAL_INPUTS,
    PROTECTED_FILE_HASHES,
    ReleaseBuildError,
    build_system_release,
    _exclusive_lock,
    _preflight_inputs,
    _promote_release,
    clean_staging,
    load_release_json,
    recover_release,
    verify_release_directory,
)


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "reports" / "release" / "current"
CLIENT = TestClient(app)
MANIFEST = json.loads((RELEASE / "release_manifest.json").read_text(encoding="utf-8"))
ACCEPTANCE = json.loads((RELEASE / "system_acceptance_report.json").read_text(encoding="utf-8"))


def _config(**changes) -> ReleaseBuildConfig:
    values = {
        "market_data_as_of": "2026-07-08",
        "decision_date": "2026-07-13",
        "generated_at": "2026-07-13T08:15:34+00:00",
        "provider": "local",
        "output_dir": "reports/release",
        "commit_sha": "6183bfdf6fcf5225ac141c6b670cda97eb00ca97",
    }
    values.update(changes)
    return ReleaseBuildConfig(**values)


@pytest.mark.parametrize(
    "field",
    [
        "release_id",
        "commit_sha",
        "market_data_as_of",
        "decision_date",
        "generated_at",
        "build_mode",
        "network_accessed",
        "inputs",
        "artifacts",
        "dependency_graph",
        "dependency_graph_hash",
        "protected_file_hashes",
        "reproducibility",
        "acceptance_report_hash",
        "raw_release_hash",
        "semantic_release_hash",
        "production_boundary",
        "verified",
        "errors",
    ],
)
def test_release_manifest_contract(field):
    assert field in MANIFEST


@pytest.mark.parametrize(
    "field",
    ["path", "role", "sha256", "semantic_hash", "source_as_of", "classification", "dependencies"],
)
@pytest.mark.parametrize("index", range(11))
def test_each_release_input_contract(index, field):
    assert field in MANIFEST["inputs"][index]


@pytest.mark.parametrize(
    "field",
    ["path", "role", "sha256", "semantic_hash", "source_as_of", "classification", "dependencies"],
)
@pytest.mark.parametrize("index", range(9))
def test_each_release_artifact_contract(index, field):
    assert field in MANIFEST["artifacts"][index]


@pytest.mark.parametrize(
    "section",
    [
        "data_integrity",
        "strategy_integrity",
        "v11_snapshot_integrity",
        "execution_integrity",
        "mapping_governance_integrity",
        "shadow_integrity",
        "current_decision_integrity",
        "identifier_integrity",
        "temporal_integrity",
        "reproducibility",
        "production_boundary",
        "api_web_contract",
        "documentation",
        "protected_files",
    ],
)
def test_acceptance_section_is_present(section):
    assert isinstance(ACCEPTANCE[section], dict)


@pytest.mark.parametrize("step", [name for name, _ in BUILD_STEPS])
def test_dependency_graph_contains_each_required_step(step):
    assert step in {row["name"] for row in dependency_graph()["steps"]}


@pytest.mark.parametrize("path", list(PROTECTED_FILE_HASHES))
def test_protected_file_matches_task_034_fix_baseline(path):
    assert sha256_file(ROOT / path) == PROTECTED_FILE_HASHES[path]


@pytest.mark.parametrize(
    "document",
    [
        "README.md",
        "docs/ARCHITECTURE.md",
        "docs/OFFLINE_BUILD.md",
        "docs/OPERATIONS.md",
        "docs/DATA_CONTRACTS.md",
        "docs/LIMITATIONS.md",
    ],
)
def test_required_document_exists(document):
    assert (ROOT / document).is_file()


@pytest.mark.parametrize(
    "route",
    ["/", "/current-decision", "/v11-current-allocation", "/research-validation", "/system-status"],
)
def test_primary_page_returns_200_and_has_five_item_navigation(route):
    response = CLIENT.get(route)
    assert response.status_code == 200
    navigation = re.search(r'<nav class="primary-nav".*?</nav>', response.text, re.DOTALL)
    assert navigation is not None
    assert navigation.group(0).count("<a ") == 5


@pytest.mark.parametrize(
    "route",
    ["/diagnosis", "/production-readiness", "/research-backtest", "/execution-backtest", "/shadow-portfolio"],
)
def test_hidden_advanced_route_remains_available_without_global_navigation(route):
    response = CLIENT.get(route)
    assert response.status_code == 200
    assert '<nav class="primary-nav"' not in response.text


@pytest.mark.parametrize(
    "route",
    ["/", "/current-decision", "/v11-current-allocation", "/research-validation", "/system-status"],
)
def test_primary_pages_have_no_form_or_automatic_execution_control(route):
    text = CLIENT.get(route).text.lower()
    assert "<form" not in text
    assert "立即买入" not in text
    assert "自动执行" not in text


@pytest.mark.parametrize(
    "phrase",
    [
        "系统发布状态",
        "普通用户建议阅读顺序",
        "现在该看什么",
        "三种结果如何理解",
        "本系统不会做什么",
        "Execution Validation 尚未通过",
        "40%",
        "medium-quality",
        "非交易指令",
        "未授权",
    ],
)
def test_home_explains_correct_use_and_boundaries(phrase):
    assert phrase in CLIENT.get("/").text


@pytest.mark.parametrize(
    "phrase",
    ["用于人工判断", "不会生成订单", "不会自动替换 V11", "已验证快照", "仅供人工审核", "非交易指令"],
)
def test_current_decision_user_boundary_copy(phrase):
    assert phrase in CLIENT.get("/current-decision").text


@pytest.mark.parametrize(
    "phrase",
    ["正式候选模型", "离线配置快照", "不是下单指令", "未授权自动交易", "Snapshot Semantic Integrity"],
)
def test_v11_user_boundary_copy(phrase):
    assert phrase in CLIENT.get("/v11-current-allocation").text


@pytest.mark.parametrize(
    "phrase",
    ["Research Backtest", "Execution Backtest", "Execution-Aware Shadow", "Mapping Evidence", "不等于真实 ETF 收益", "不是生产组合"],
)
def test_research_validation_explains_each_layer(phrase):
    assert phrase in CLIENT.get("/research-validation").text


@pytest.mark.parametrize(
    "phrase",
    ["Release ID", "Build Mode", "Market Data As-Of", "Decision Date", "Reproducibility", "Data Integrity", "V11 Integrity", "Execution Validation", "Mapping Governance", "Shadow Integrity", "Current Decision Status", "Production Boundary", "已知非阻塞条件", "阻塞错误", "文档入口"],
)
def test_system_status_has_required_sections(phrase):
    assert phrase in CLIENT.get("/system-status").text


def test_release_is_verified_and_reproducible():
    status = verify_release_directory(RELEASE)
    assert status["verified"] is True
    assert MANIFEST["reproducibility"]["verified"] is True
    assert MANIFEST["reproducibility"]["first_build_hash"] == MANIFEST["reproducibility"]["second_build_hash"]
    assert MANIFEST["reproducibility"]["artifact_hash_differences"] == []


def test_release_generated_at_is_explicit_and_deterministic():
    assert MANIFEST["generated_at"] == "2026-07-13T08:15:34+00:00"
    for name in ("v11_current_allocation.json", "current_market_decision.json", "system_acceptance_report.json"):
        assert json.loads((RELEASE / name).read_text(encoding="utf-8"))["generated_at"] == MANIFEST["generated_at"]


def test_release_hashes_are_recomputable():
    assert MANIFEST["dependency_graph_hash"] == dependency_graph_hash()
    assert sha256_file(RELEASE / "system_acceptance_report.json") == MANIFEST["acceptance_report_hash"]
    for row in MANIFEST["artifacts"]:
        assert sha256_file(RELEASE / row["path"]) == row["sha256"]
        assert semantic_hash(json.loads((RELEASE / row["path"]).read_text(encoding="utf-8"))) == row["semantic_hash"]


def test_release_production_boundary_is_fail_closed():
    boundary = MANIFEST["production_boundary"]
    assert boundary["production_actionable"] is False
    assert boundary["trading_instruction"] is False
    assert boundary["shadow_production_approved"] is False
    assert boundary["execution_validation_ready"] is False
    assert boundary["forbidden_field_paths"] == []


def test_execution_false_is_explicit_nonblocking_evidence():
    execution = ACCEPTANCE["execution_integrity"]
    assert execution["verified"] is True
    assert execution["execution_validation_ready"] is False
    assert execution["nonblocking_when_not_ready"] is True
    assert execution["reasons"]
    assert ACCEPTANCE["system_acceptance_passed"] is True


def test_api_reads_release_without_triggering_build():
    manifest = CLIENT.get("/api/system/release-manifest")
    acceptance = CLIENT.get("/api/system/acceptance")
    assert manifest.status_code == acceptance.status_code == 200
    assert manifest.json()["release_id"] == MANIFEST["release_id"]
    assert acceptance.json()["system_acceptance_passed"] is True


def test_missing_release_loader_returns_available_false(tmp_path):
    assert load_release_json("release_manifest.json", root=tmp_path)["available"] is False


def test_invalid_release_loader_returns_available_false(tmp_path):
    path = tmp_path / "reports" / "release" / "current" / "release_manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")
    assert load_release_json("release_manifest.json", root=tmp_path)["available"] is False


def test_local_provider_is_mandatory():
    with pytest.raises(ValueError, match="provider must be local"):
        _config(provider="mock").validate()


def test_market_data_cannot_look_forward():
    with pytest.raises(ValueError, match="must not be after"):
        _config(market_data_as_of="2026-07-14").validate()


def test_generated_at_requires_timezone():
    with pytest.raises(ValueError, match="timezone"):
        _config(generated_at="2026-07-13T08:15:34").validate()


def test_missing_local_input_fails_preflight(tmp_path):
    inputs, errors = _preflight_inputs(tmp_path, _config())
    assert inputs == []
    assert any("required local input missing" in error for error in errors)


def test_preflight_failure_records_staging_error_and_preserves_current(tmp_path):
    current = tmp_path / "reports" / "release" / "current"
    current.mkdir(parents=True)
    (current / "sentinel.txt").write_text("unchanged", encoding="utf-8")
    with pytest.raises(ReleaseBuildError, match="preflight"):
        build_system_release(_config(), root=tmp_path)
    failures = list((tmp_path / "reports" / ".release-staging").glob("failed-*/failure.json"))
    assert len(failures) == 1
    assert json.loads(failures[0].read_text(encoding="utf-8"))["phase"] == "local_input_preflight"
    assert (current / "sentinel.txt").read_text(encoding="utf-8") == "unchanged"


def test_release_orchestrator_has_no_live_provider_import_path():
    source = (ROOT / "release" / "orchestrator.py").read_text(encoding="utf-8")
    assert "TushareProvider" not in source
    assert "yfinance" not in source
    assert "fredapi" not in source
    assert "build_mock" not in source


def test_exclusive_release_lock_rejects_concurrent_build(tmp_path):
    lock = tmp_path / "release.lock"
    with _exclusive_lock(lock):
        with pytest.raises(ReleaseBuildError, match="exclusive lock"):
            with _exclusive_lock(lock):
                pass
    assert not lock.exists()


def test_invalid_candidate_does_not_replace_current(tmp_path):
    release_root = tmp_path / "release"
    current = release_root / "current"
    candidate = tmp_path / "candidate"
    current.mkdir(parents=True)
    candidate.mkdir()
    (current / "sentinel.txt").write_text("current", encoding="utf-8")
    with pytest.raises(ReleaseBuildError):
        _promote_release(candidate, release_root, "test-release")
    assert (current / "sentinel.txt").read_text(encoding="utf-8") == "current"


def test_recovery_restores_verified_previous_release(tmp_path):
    release_root = tmp_path / "reports" / "release"
    shutil.copytree(RELEASE, release_root / "previous")
    (release_root / "current").mkdir()
    (release_root / "current" / "broken.txt").write_text("broken", encoding="utf-8")
    result = recover_release(root=tmp_path)
    assert result["recovered"] is True
    assert verify_release_directory(release_root / "current")["verified"] is True


def test_staging_cleanup_retains_failures_by_default(tmp_path):
    staging = tmp_path / "reports" / ".release-staging"
    (staging / "complete").mkdir(parents=True)
    (staging / "failed").mkdir()
    (staging / "failed" / "failure.json").write_text("{}", encoding="utf-8")
    result = clean_staging(root=tmp_path)
    assert result == {"removed": ["complete"], "retained": ["failed"]}


@pytest.mark.parametrize(
    "mutator, expected",
    [
        (lambda rows: rows + [{"legacy_asset_id": "510300.SH", "canonical_instrument_id": "512760.SH", "instrument_type": "etf", "source": "test"}], "shadowing"),
        (lambda rows: rows + [{"legacy_asset_id": "512760.SH", "canonical_instrument_id": "510300.SH", "instrument_type": "etf", "source": "test"}], "shadowing"),
        (lambda rows: [{**rows[0], "instrument_type": "stock"}] + rows[1:], "instrument type is invalid"),
        (lambda rows: [{**rows[0], "source": ""}] + rows[1:], "source is invalid"),
        (lambda rows: [{**rows[0], "canonical_instrument_id": "510300"}] + rows[1:], "format is invalid"),
    ],
)
def test_alias_graph_and_metadata_fail_closed(tmp_path, mutator, expected):
    registry = json.loads((ROOT / "data" / "universe" / "execution_instrument_aliases.json").read_text(encoding="utf-8"))
    registry["aliases"] = mutator(registry["aliases"])
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    result = load_execution_instrument_aliases(path)
    assert result["verified"] is False
    assert any(expected in error for error in result["errors"])


@pytest.mark.parametrize(
    "integrity_change",
    [
        {"verified": False},
        {"semantic_verified": False},
        {"snapshot_payload_hash": "bad"},
        {"actual_snapshot_payload_hash": "0" * 64},
    ],
)
def test_current_decision_explicit_snapshot_integrity_gate(integrity_change):
    sources = load_current_market_sources()
    diagnosis = sources["diagnosis"]
    snapshot = copy.deepcopy(sources["v11_allocation"])
    snapshot["source_integrity"].update(integrity_change)
    candidate = _production_candidate(diagnosis, snapshot, snapshot_present=True)
    assert candidate["allocation_available"] is False
    assert candidate["snapshot_integrity_verified"] is False


def test_route_inventory_and_cleanup_prove_final_visibility():
    inventory = json.loads((RELEASE / "ui_route_inventory.json").read_text(encoding="utf-8"))
    cleanup = json.loads((RELEASE / "legacy_cleanup_report.json").read_text(encoding="utf-8"))
    assert inventory["primary_navigation_count"] == 5
    assert cleanup["visible_link_count_after"] == 5
    assert cleanup["visible_link_count_after"] < cleanup["visible_link_count_before"]
    assert cleanup["proof"] == {
        "import_scan_passed": True,
        "route_reference_scan_passed": True,
        "test_reference_scan_passed": True,
        "release_dependency_scan_passed": True,
    }


def test_documented_rebuild_command_is_exact_and_executable_help():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    command = "python scripts/build_system_release.py --market-data-as-of 2026-07-08 --decision-date 2026-07-13 --generated-at 2026-07-13T08:15:34+00:00 --provider local --output-dir reports/release"
    assert command in readme
    assert (ROOT / "scripts" / "build_system_release.py").is_file()


def test_formal_decision_artifacts_have_no_production_fields():
    for name in ("v11_current_allocation.json", "current_market_decision.json", "execution_aware_shadow_portfolio.json"):
        assert forbidden_field_paths(json.loads((RELEASE / name).read_text(encoding="utf-8"))) == []


def test_system_status_mandatory_warning_is_exact():
    text = CLIENT.get("/system-status").text
    assert "This system status page verifies a reproducible local decision-support release. It does not authorize automated trading." in text


def test_home_release_failure_hides_current_decision_primary_action(monkeypatch):
    import backend.main as main_module

    def unavailable(name):
        return {"available": False, "verified": False, "blocking_errors": ["release integrity failed"]}

    monkeypatch.setattr(main_module, "load_release_json", unavailable)
    html = main_module.system_home()
    assert "当前结论不可依赖" in html
    assert 'class="button primary" href="/system-status"' in html
    assert 'class="button primary" href="/current-decision"' not in html
