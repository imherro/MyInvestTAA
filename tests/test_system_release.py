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
    REQUIRED_ACCEPTANCE_GATES,
    ReleaseBuildError,
    build_system_release,
    _build_base_candidate,
    _candidate_content_hashes,
    _exclusive_lock,
    _preflight_inputs,
    _promote_release,
    clean_staging,
    load_release_json,
    load_committed_counterfactual_report,
    recover_release,
    verify_release_directory,
)
from release.web_contracts import (
    PRIMARY_NAVIGATION,
    build_legacy_cleanup_report,
    build_route_inventory,
    scan_backend_web_routes,
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
@pytest.mark.parametrize("index", range(len(MANIFEST["inputs"])))
def test_each_release_input_contract(index, field):
    assert field in MANIFEST["inputs"][index]


@pytest.mark.parametrize(
    "field",
    ["path", "role", "sha256", "semantic_hash", "source_as_of", "classification", "dependencies"],
)
@pytest.mark.parametrize("index", range(len(MANIFEST["artifacts"])))
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
    assert MANIFEST["reproducibility"]["first_candidate_raw_hash"] == MANIFEST["reproducibility"]["second_candidate_raw_hash"]
    assert MANIFEST["reproducibility"]["first_candidate_semantic_hash"] == MANIFEST["reproducibility"]["second_candidate_semantic_hash"]
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
    assert cleanup["verified"] is True
    assert all(section["verified"] is True for section in cleanup["proof"].values())
    assert cleanup["proof"]["route_scan"]["scanned_count"] == 26
    assert cleanup["proof"]["route_scan"]["unclassified_routes"] == []


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


@pytest.mark.parametrize(
    "route,artifact",
    [
        ("/api/decision/current-market", "current_market_decision.json"),
        ("/api/decision/v11-current-allocation", "v11_current_allocation.json"),
    ],
)
def test_formal_decision_apis_return_committed_release_artifacts(route, artifact):
    assert CLIENT.get(route).json() == {
        **json.loads((RELEASE / artifact).read_text(encoding="utf-8")),
        "available": True,
    }


def test_counterfactual_api_reads_verified_committed_audit_artifact():
    payload = CLIENT.get("/api/research/execution-mapping-counterfactual").json()
    committed = json.loads((RELEASE / "execution_mapping_counterfactual_report.json").read_text(encoding="utf-8"))
    assert payload["available"] is True
    assert payload["status"] == "current"
    assert payload["release_scope"] == "committed_release"
    assert payload["input_contract_verification"]["verified"] is True
    assert payload["impact"] == committed["impact"]
    assert any(row["path"] == "execution_mapping_counterfactual_report.json" for row in MANIFEST["artifacts"])
    assert committed["release_scope"] == "committed_release"
    assert ACCEPTANCE["counterfactual_integrity"]["verified"] is True
    assert "counterfactual_integrity" in ACCEPTANCE["required_gates"]


def test_stale_counterfactual_cannot_enter_release(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "release.orchestrator.load_counterfactual_report",
        lambda *_: {"available": True, "status": "stale", "input_contract_verification": {"verified": False, "errors": ["proposal drift"]}},
    )
    with pytest.raises(ReleaseBuildError, match="counterfactual audit artifact is unavailable or stale"):
        _build_base_candidate(tmp_path / "candidate", ROOT, _config())


@pytest.mark.parametrize("field,value", [("impact", {"annual_return_delta": 9}), ("decision", {"ready_for_manual_mapping_approval": True}), ("delta_contract", {"display_values": {"annual_return_delta": 999}})])
def test_committed_counterfactual_tampering_fails_closed(tmp_path, field, value):
    target = tmp_path / "reports" / "release" / "current"
    shutil.copytree(RELEASE, target)
    path = target / "execution_mapping_counterfactual_report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    _write_json(path, payload)
    loaded = load_committed_counterfactual_report(root=tmp_path)
    assert loaded["available"] is False
    assert loaded["status"] == "unavailable"
    assert loaded["message"] == "committed system release integrity failed"


@pytest.mark.parametrize("control", ["COMMITTED.json", "release_manifest.json", "system_acceptance_report.json"])
def test_missing_release_control_file_blocks_counterfactual_without_fallback(tmp_path, control):
    target = tmp_path / "reports" / "release" / "current"
    shutil.copytree(RELEASE, target)
    (target / control).unlink()
    mutable = tmp_path / "reports" / "execution_mapping_counterfactual_report.json"
    mutable.parent.mkdir(parents=True, exist_ok=True)
    mutable.write_text((RELEASE / "execution_mapping_counterfactual_report.json").read_text(encoding="utf-8"), encoding="utf-8")
    loaded = load_committed_counterfactual_report(root=tmp_path)
    assert loaded["available"] is False
    assert loaded["message"] == "committed system release integrity failed"


@pytest.mark.parametrize(
    "route,labels",
    [
        (
            "/current-decision",
            (
                "510500.SH 中证500ETF",
                "512760.SH 半导体ETF",
                "588000.SH 科创50ETF",
            ),
        ),
        (
            "/current-decision",
            (
                "510300.SH 沪深300ETF",
                "512100.SH 中证1000ETF",
                "518880.SH 黄金ETF",
                "512010.SH 医药ETF",
                "512170.SH 医疗ETF",
            ),
        ),
        (
            "/shadow-portfolio",
            (
                "510500.SH 中证500ETF",
                "512760.SH 半导体ETF",
                "588000.SH 科创50ETF",
            ),
        ),
    ],
)
def test_html_pages_label_etf_codes_with_registered_names(route, labels):
    text = CLIENT.get(route).text
    for label in labels:
        assert label in text


def test_etf_display_labels_do_not_change_json_api_contract():
    text = CLIENT.get("/api/decision/current-market").text
    assert "510500.SH" in text
    assert "510500.SH 中证500ETF" not in text


def test_home_release_failure_hides_current_decision_primary_action(monkeypatch):
    import backend.main as main_module

    def unavailable(name):
        return {"available": False, "verified": False, "blocking_errors": ["release integrity failed"]}

    monkeypatch.setattr(main_module, "load_release_json", unavailable)
    html = main_module.system_home()
    assert "当前结论不可依赖" in html
    assert 'class="button primary" href="/system-status"' in html
    assert 'class="button primary" href="/current-decision"' not in html


def _copied_release(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(RELEASE, root / "reports" / "release" / "current")
    return root


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resign_manifest(directory: Path, manifest: dict) -> None:
    manifest_path = directory / "release_manifest.json"
    _write_json(manifest_path, manifest)
    marker = json.loads((directory / "COMMITTED.json").read_text(encoding="utf-8"))
    marker["release_manifest_hash"] = sha256_file(manifest_path)
    _write_json(directory / "COMMITTED.json", marker)


@pytest.mark.parametrize(
    "target, mutate",
    [
        ("release_manifest.json", lambda value: value.update({"generated_at": "2026-07-13T08:15:35+00:00"})),
        ("system_acceptance_report.json", lambda value: value.update({"generated_at": "2026-07-13T08:15:35+00:00"})),
        ("current_market_decision.json", lambda value: value.update({"status": "tampered"})),
        ("COMMITTED.json", lambda value: value.update({"release_id": "tampered-release"})),
    ],
)
def test_committed_loader_rejects_valid_json_tampering(tmp_path, target, mutate):
    root = _copied_release(tmp_path)
    path = root / "reports" / "release" / "current" / target
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    _write_json(path, value)
    result = load_release_json("release_manifest.json", root=root)
    assert result["available"] is False
    assert result["message"] == "committed system release integrity failed"
    assert result["errors"]


def test_committed_loader_rejects_missing_marker(tmp_path):
    root = _copied_release(tmp_path)
    (root / "reports" / "release" / "current" / "COMMITTED.json").unlink()
    result = load_release_json("system_acceptance_report.json", root=root)
    assert result["available"] is False
    assert result["message"] == "committed system release integrity failed"


def test_custom_loader_can_explicitly_disable_committed_verification(tmp_path):
    path = tmp_path / "reports" / "release" / "current" / "sample.json"
    path.parent.mkdir(parents=True)
    _write_json(path, {"value": 1})
    assert load_release_json("sample.json", root=tmp_path, verify_committed=False) == {
        "value": 1,
        "available": True,
    }


@pytest.mark.parametrize(
    "field,error",
    [
        ("raw_release_hash", "raw release hash mismatch"),
        ("semantic_release_hash", "semantic release hash mismatch"),
        ("dependency_graph_hash", "dependency graph hash mismatch"),
    ],
)
def test_release_level_hash_tampering_is_recomputed(tmp_path, field, error):
    root = _copied_release(tmp_path)
    directory = root / "reports" / "release" / "current"
    manifest = json.loads((directory / "release_manifest.json").read_text(encoding="utf-8"))
    manifest[field] = "0" * 64
    _resign_manifest(directory, manifest)
    result = verify_release_directory(directory)
    assert result["verified"] is False
    assert error in result["errors"]


def test_semantic_artifact_hash_tampering_is_recomputed(tmp_path):
    root = _copied_release(tmp_path)
    directory = root / "reports" / "release" / "current"
    manifest = json.loads((directory / "release_manifest.json").read_text(encoding="utf-8"))
    row = next(item for item in manifest["artifacts"] if item["path"] == "current_market_decision.json")
    row["semantic_hash"] = "0" * 64
    manifest["semantic_release_hash"] = semantic_hash({item["path"]: item["semantic_hash"] for item in manifest["artifacts"]})
    _resign_manifest(directory, manifest)
    result = verify_release_directory(directory)
    assert result["verified"] is False
    assert "artifact semantic hash mismatch: current_market_decision.json" in result["errors"]


def test_missing_artifact_dependency_is_rejected(tmp_path):
    root = _copied_release(tmp_path)
    directory = root / "reports" / "release" / "current"
    manifest = json.loads((directory / "release_manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"][0]["dependencies"].append("missing.json")
    _resign_manifest(directory, manifest)
    result = verify_release_directory(directory)
    assert result["verified"] is False
    assert any("artifact dependency missing" in error for error in result["errors"])


def test_duplicate_manifest_paths_are_rejected(tmp_path):
    root = _copied_release(tmp_path)
    directory = root / "reports" / "release" / "current"
    manifest = json.loads((directory / "release_manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"].append(copy.deepcopy(manifest["artifacts"][0]))
    _resign_manifest(directory, manifest)
    result = verify_release_directory(directory)
    assert result["verified"] is False
    assert "duplicate artifact path" in result["errors"]


@pytest.mark.parametrize(
    "target,value,error",
    [
        ("release_manifest.json", [], "release JSON invalid: ValueError"),
        ("system_acceptance_report.json", [], "release JSON invalid: ValueError"),
        ("COMMITTED.json", [], "release JSON invalid: ValueError"),
        ("release_manifest.json", {"artifacts": [{"path": []}], "inputs": []}, "artifact path must be a string"),
    ],
)
def test_structurally_invalid_control_json_fails_closed(tmp_path, target, value, error):
    root = _copied_release(tmp_path)
    directory = root / "reports" / "release" / "current"
    _write_json(directory / target, value)
    result = verify_release_directory(directory)
    assert result["verified"] is False
    assert error in result["errors"]


def test_acceptance_release_id_mismatch_is_rejected_even_when_hashes_are_updated(tmp_path):
    root = _copied_release(tmp_path)
    directory = root / "reports" / "release" / "current"
    acceptance_path = directory / "system_acceptance_report.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["release_id"] = "different-release"
    _write_json(acceptance_path, acceptance)
    manifest = json.loads((directory / "release_manifest.json").read_text(encoding="utf-8"))
    acceptance_row = next(item for item in manifest["artifacts"] if item["path"] == "system_acceptance_report.json")
    acceptance_row["sha256"] = sha256_file(acceptance_path)
    acceptance_row["semantic_hash"] = semantic_hash(acceptance)
    manifest["acceptance_report_hash"] = acceptance_row["sha256"]
    manifest["raw_release_hash"] = semantic_hash({item["path"]: item["sha256"] for item in manifest["artifacts"]})
    manifest["semantic_release_hash"] = semantic_hash({item["path"]: item["semantic_hash"] for item in manifest["artifacts"]})
    _resign_manifest(directory, manifest)
    result = verify_release_directory(directory)
    assert result["verified"] is False
    assert "acceptance release ID mismatch" in result["errors"]


def test_failed_acceptance_gate_is_rejected_even_when_all_hashes_are_updated(tmp_path):
    root = _copied_release(tmp_path)
    directory = root / "reports" / "release" / "current"
    acceptance_path = directory / "system_acceptance_report.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["reproducibility"]["verified"] = False
    acceptance["system_acceptance_passed"] = True
    _write_json(acceptance_path, acceptance)
    manifest = json.loads((directory / "release_manifest.json").read_text(encoding="utf-8"))
    manifest["reproducibility"]["verified"] = False
    row = next(item for item in manifest["artifacts"] if item["path"] == "system_acceptance_report.json")
    row["sha256"] = sha256_file(acceptance_path)
    row["semantic_hash"] = semantic_hash(acceptance)
    manifest["acceptance_report_hash"] = row["sha256"]
    manifest["raw_release_hash"] = semantic_hash({item["path"]: item["sha256"] for item in manifest["artifacts"]})
    manifest["semantic_release_hash"] = semantic_hash({item["path"]: item["semantic_hash"] for item in manifest["artifacts"]})
    _resign_manifest(directory, manifest)
    result = verify_release_directory(directory)
    assert result["verified"] is False
    assert "release reproducibility is not verified" in result["errors"]
    assert "acceptance gate failed: reproducibility" in result["errors"]


def test_staged_v11_is_actual_current_decision_input_and_root_loader_is_not_called(tmp_path, monkeypatch):
    import decision.current_market.sources as source_module

    def forbidden_root_loader(*args, **kwargs):
        raise AssertionError("root V11 loader must not be called")

    monkeypatch.setattr(source_module, "load_v11_current_allocation", forbidden_root_loader)
    directory = tmp_path / "candidate"
    base = _build_base_candidate(directory, ROOT, _config())
    current = base["current"]
    v11 = base["v11"]
    dependency = current["release_dependencies"]["v11_current_allocation"]
    assert current["production_candidate"]["allocation"] == v11["allocation"]
    assert dependency["sha256"] == sha256_file(directory / "v11_current_allocation.json")
    assert current["source_manifest"]["v11_current_allocation"]["sha256"] == dependency["sha256"]
    assert current["source_manifest"]["v11_current_allocation"]["release_artifact_path"] == "v11_current_allocation.json"
    assert current["production_candidate"]["release_artifact_dependency"] == "v11_current_allocation.json"


def test_real_candidate_hashes_come_from_base_artifact_content(tmp_path):
    directory = tmp_path / "candidate"
    _build_base_candidate(directory, ROOT, _config())
    raw_hash, semantic_candidate_hash = _candidate_content_hashes(directory)
    assert raw_hash == MANIFEST["reproducibility"]["first_candidate_raw_hash"]
    assert semantic_candidate_hash == MANIFEST["reproducibility"]["first_candidate_semantic_hash"]


def test_acceptance_required_gate_list_is_complete():
    assert ACCEPTANCE["required_gates"] == list(REQUIRED_ACCEPTANCE_GATES)
    assert all(ACCEPTANCE[name]["verified"] is True for name in REQUIRED_ACCEPTANCE_GATES)


def test_actual_route_scan_has_no_unknown_pages():
    routes = scan_backend_web_routes(ROOT)
    inventory = build_route_inventory(routes)
    assert len(routes) == 26
    assert inventory["verified"] is True
    assert inventory["unclassified_routes"] == []


def test_unknown_web_route_fails_inventory_and_cleanup():
    inventory = build_route_inventory(scan_backend_web_routes(ROOT) + ["/unknown-user-page"])
    cleanup = build_legacy_cleanup_report(ROOT, inventory)
    assert inventory["verified"] is False
    assert inventory["unclassified_routes"] == ["/unknown-user-page"]
    assert cleanup["verified"] is False
    assert cleanup["proof"]["route_scan"]["verified"] is False


def test_hidden_route_reentering_primary_navigation_fails_cleanup(monkeypatch):
    import release.web_contracts as web_contracts

    inventory = build_route_inventory(scan_backend_web_routes(ROOT))
    monkeypatch.setattr(
        web_contracts,
        "PRIMARY_NAVIGATION",
        PRIMARY_NAVIGATION + (("/diagnosis", "错误一级入口", "不应出现"),),
    )
    cleanup = build_legacy_cleanup_report(ROOT, inventory)
    assert cleanup["verified"] is False
    assert "/diagnosis" in cleanup["proof"]["reference_scan"]["hidden_or_archived_in_primary"]


def _assert_failed_build_never_promotes(monkeypatch, tmp_path, *, web_failure=False):
    import release.orchestrator as orchestrator

    promoted = []
    output_dir = f"temp/{tmp_path.name}-release"
    staging_root = ROOT / "reports" / ".release-staging"
    staging_before = set(staging_root.iterdir()) if staging_root.exists() else set()
    monkeypatch.setattr(orchestrator, "_promote_release", lambda *args: promoted.append(args))
    if web_failure:
        monkeypatch.setattr(
            orchestrator,
            "validate_web_contract",
            lambda *args: {"verified": False, "errors": ["simulated Web contract failure"]},
        )
    else:
        monkeypatch.setattr(
            orchestrator,
            "_directory_hash_differences",
            lambda *args: [{"path": "simulated.json", "first": "a", "second": "b"}],
        )
    try:
        with pytest.raises(ReleaseBuildError):
            build_system_release(_config(output_dir=output_dir), root=ROOT)
        assert promoted == []
        assert not (ROOT / output_dir / "current").exists()
    finally:
        shutil.rmtree(ROOT / output_dir, ignore_errors=True)
        if staging_root.exists():
            for path in set(staging_root.iterdir()) - staging_before:
                shutil.rmtree(path, ignore_errors=True)


def test_reproducibility_failure_blocks_promotion(monkeypatch, tmp_path):
    _assert_failed_build_never_promotes(monkeypatch, tmp_path)


def test_web_contract_failure_blocks_promotion(monkeypatch, tmp_path):
    _assert_failed_build_never_promotes(monkeypatch, tmp_path, web_failure=True)
