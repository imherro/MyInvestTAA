from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile

from backtest.execution.approval_integrity import validate_approval_integrity
from backtest.execution.proposal_report import COUNTER, load_counterfactual_report
from decision.current_market import build_current_market_decision, load_current_market_sources
from decision.v11_current import build_v11_current_allocation_snapshot
from decision.v11_current.validation import validate_v11_current_allocation_snapshot
from engine.asset_registry.loader import ROOT
from release.build_graph import dependency_graph, dependency_graph_hash
from release.contracts import (
    forbidden_field_paths,
    read_json,
    semantic_hash,
    sha256_file,
    validate_alias_registry,
    validate_temporal_contract,
    write_json,
)
from release.models import ReleaseBuildConfig, SourceDefinition
from release.web_contracts import (
    build_legacy_cleanup_report,
    build_route_inventory,
    scan_backend_web_routes,
    validate_web_contract,
)


PROTECTED_BASELINE_COMMIT = "6183bfdf6fcf5225ac141c6b670cda97eb00ca97"
PROTECTED_FILE_HASHES = {
    "backtest/taa/engine.py": "021f4ca11c9d7558e9b77424dff62919ec4890fcdf42b3cdbda9eac5380f2704",
    "data_pipeline/strategy_diagnosis.py": "527ce8b117103b4c4192aeb57755dc2ca27cfc5ce13b4a0b4ef801fcf3444ed2",
    "config/execution_validation_policy.json": "e7e30a5633c781b8a7541fa3518fbd7d4b3cf89188c1d0a530d626c695071771",
    "data/universe/asset_mapping.json": "8b9ee650f036bfd675a1cf19548b62293efd0d282e9013c705f1e42e3525cfb8",
    "data/universe/execution_mapping_decision_ledger.json": "8da78db353ffc958d92cd4f81a545566c244bafd3600bd7f6141f5971108a33b",
}

LOCAL_INPUTS = (
    SourceDefinition("reports/strategy_diagnosis_report.json", "canonical strategy diagnosis", "verified_external_local_input", "2026-07-08"),
    SourceDefinition("reports/research_backtest_report.json", "research backtest evidence", "verified_external_local_input", "2026-07-08"),
    SourceDefinition("reports/execution_backtest_report.json", "execution backtest evidence", "verified_external_local_input", "2026-07-08"),
    SourceDefinition("reports/execution_aware_shadow_portfolio.json", "execution-aware shadow snapshot", "verified_external_local_input", "2026-07-08"),
    SourceDefinition("reports/execution_mapping_proposal.json", "counterfactual proposal input", "verified_external_local_input", "2026-07-08"),
    SourceDefinition("reports/execution_mapping_counterfactual_report.json", "counterfactual audit evidence", "verified_external_local_input", "2026-07-08"),
    SourceDefinition("reports/execution_price_dataset_manifest.json", "execution price provenance", "verified_external_local_input", "2026-07-08"),
    SourceDefinition("reports/execution_mapping_approval_integrity_seal.json", "approval integrity seal", "immutable_governance_artifact", "2026-07-13"),
    SourceDefinition("reports/execution_mapping_approval_record.json", "approved mapping record", "immutable_governance_artifact", "2026-07-13"),
    SourceDefinition("data/universe/asset_mapping.json", "research-to-execution registry", "immutable_governance_artifact"),
    SourceDefinition("data/universe/execution_mapping_decision_ledger.json", "mapping decision ledger", "immutable_governance_artifact"),
    SourceDefinition("data/universe/execution_instrument_aliases.json", "canonical instrument identity registry", "immutable_governance_artifact"),
    SourceDefinition("config/execution_validation_policy.json", "execution validation gate policy", "immutable_governance_artifact"),
)

COPIED_REPORTS = (
    "strategy_diagnosis_report.json",
    "research_backtest_report.json",
    "execution_backtest_report.json",
    "execution_aware_shadow_portfolio.json",
    "execution_mapping_counterfactual_report.json",
)

REQUIRED_ACCEPTANCE_GATES = (
    "data_integrity",
    "strategy_integrity",
    "v11_snapshot_integrity",
    "execution_integrity",
    "mapping_governance_integrity",
    "shadow_integrity",
    "current_decision_integrity",
    "identifier_integrity",
    "temporal_integrity",
    "production_boundary",
    "reproducibility",
    "api_web_contract",
    "ui_information_architecture",
    "legacy_cleanup",
    "documentation",
    "protected_files",
)


def build_system_release(config: ReleaseBuildConfig, *, root: Path = ROOT) -> dict:
    config.validate()
    release_root = (root / config.output_dir).resolve()
    staging_root = root / "reports" / ".release-staging"
    release_root.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(release_root / ".build.lock"):
        inputs, preflight_errors = _preflight_inputs(root, config)
        if preflight_errors:
            failure_id = semantic_hash(
                {"config": config.as_dict(), "errors": preflight_errors}
            )[:12]
            failed_root = Path(
                tempfile.mkdtemp(prefix=f"failed-{failure_id}-", dir=staging_root)
            )
            write_json(
                failed_root / "failure.json",
                {
                    "status": "failed",
                    "phase": "local_input_preflight",
                    "errors": preflight_errors,
                },
            )
            raise ReleaseBuildError("local input preflight failed", preflight_errors)
        fingerprint = semantic_hash(
            {"config": config.as_dict(), "inputs": inputs, "graph": dependency_graph_hash()}
        )
        release_id = f"taa-{config.decision_date.replace('-', '')}-{fingerprint[:12]}"
        build_root = Path(
            tempfile.mkdtemp(prefix=f"{release_id}-", dir=staging_root)
        )
        first = build_root / "first"
        second = build_root / "second"
        try:
            first_context = _build_base_candidate(first, root, config)
            second_context = _build_base_candidate(second, root, config)
            differences = _directory_hash_differences(first, second)
            first_raw, first_semantic = _candidate_content_hashes(first)
            second_raw, second_semantic = _candidate_content_hashes(second)
            reproducibility = {
                "verified": not differences
                and first_raw == second_raw
                and first_semantic == second_semantic,
                "input_fingerprint": fingerprint,
                "first_candidate_raw_hash": first_raw,
                "second_candidate_raw_hash": second_raw,
                "first_candidate_semantic_hash": first_semantic,
                "second_candidate_semantic_hash": second_semantic,
                "artifact_hash_differences": differences,
            }
            if not reproducibility["verified"]:
                failure = {
                    "status": "failed",
                    "release_id": release_id,
                    "errors": ["two-build reproducibility check failed"],
                    "artifact_hash_differences": differences,
                }
                write_json(build_root / "failure.json", failure)
                raise ReleaseBuildError(failure["errors"][0], differences)
            first_summary = _finalize_candidate(
                first,
                root,
                config,
                release_id,
                inputs,
                reproducibility,
                first_context,
            )
            _finalize_candidate(
                second,
                root,
                config,
                release_id,
                inputs,
                reproducibility,
                second_context,
            )
            final_differences = _directory_hash_differences(first, second)
            if final_differences:
                raise ReleaseBuildError(
                    "finalized candidates are not reproducible", final_differences
                )
            first_verification = verify_release_directory(first)
            second_verification = verify_release_directory(second)
            if not first_verification["verified"] or not second_verification["verified"]:
                raise ReleaseBuildError(
                    "finalized candidate verification failed",
                    first_verification["errors"] + second_verification["errors"],
                )
            _promote_release(first, release_root, release_id)
            shutil.rmtree(second, ignore_errors=True)
            if build_root.exists() and not any(build_root.iterdir()):
                build_root.rmdir()
            current = release_root / "current"
            return {
                **first_summary,
                "release_id": release_id,
                "release_dir": str(current),
                "reproducibility": reproducibility,
                "manifest_sha256": sha256_file(current / "release_manifest.json"),
            }
        except Exception as exc:
            if not (build_root / "failure.json").exists():
                write_json(
                    build_root / "failure.json",
                    {"status": "failed", "release_id": release_id, "errors": [str(exc)]},
                )
            raise


def load_release_json(
    name: str,
    *,
    root: Path = ROOT,
    verify_committed: bool = True,
) -> dict:
    current = root / "reports" / "release" / "current"
    path = current / name
    if verify_committed:
        status = verify_release_directory(current)
        if not status.get("verified"):
            return {
                "available": False,
                "verified": False,
                "message": "committed system release integrity failed",
                "errors": status.get("errors", []),
            }
    if not path.exists():
        return {"available": False, "verified": False, "message": f"{name} is unavailable"}
    try:
        value = read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "available": False,
            "verified": False,
            "message": f"{name} is invalid: {type(exc).__name__}",
        }
    value.setdefault("available", True)
    return value


def verify_release_directory(directory: Path) -> dict:
    manifest_path = directory / "release_manifest.json"
    acceptance_path = directory / "system_acceptance_report.json"
    marker_path = directory / "COMMITTED.json"
    if not all(path.exists() for path in (manifest_path, acceptance_path, marker_path)):
        return {"available": False, "verified": False, "errors": ["release files are missing"]}
    try:
        manifest = read_json(manifest_path)
        acceptance = read_json(acceptance_path)
        marker = read_json(marker_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {"available": False, "verified": False, "errors": [f"release JSON invalid: {type(exc).__name__}"]}
    if not all(isinstance(value, dict) for value in (manifest, acceptance, marker)):
        return {
            "available": True,
            "verified": False,
            "errors": ["release control files must be JSON objects"],
        }
    errors: list[str] = []
    artifacts = manifest.get("artifacts", [])
    inputs = manifest.get("inputs", [])
    if not isinstance(artifacts, list) or not isinstance(inputs, list):
        return {"available": True, "verified": False, "errors": ["manifest inputs and artifacts must be lists"], "manifest": manifest, "acceptance": acceptance}
    artifact_paths = [
        row.get("path")
        for row in artifacts
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    ]
    input_paths = [
        row.get("path")
        for row in inputs
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    ]
    if len(artifact_paths) != len(artifacts):
        errors.append("artifact path must be a string")
    if len(input_paths) != len(inputs):
        errors.append("input path must be a string")
    if len(artifact_paths) != len(set(artifact_paths)):
        errors.append("duplicate artifact path")
    if len(input_paths) != len(set(input_paths)):
        errors.append("duplicate input path")
    artifact_path_set = set(artifact_paths)
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            errors.append("artifact manifest entry must be an object")
            continue
        relative = artifact.get("path")
        if not isinstance(relative, str) or not relative:
            continue
        path = (directory / relative).resolve()
        try:
            path.relative_to(directory.resolve())
        except ValueError:
            errors.append(f"artifact path escapes release: {relative}")
            continue
        if not path.exists() or sha256_file(path) != artifact.get("sha256"):
            errors.append(f"artifact integrity failed: {relative}")
            continue
        try:
            value = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            errors.append(f"artifact JSON invalid: {relative}")
            continue
        if semantic_hash(value) != artifact.get("semantic_hash"):
            errors.append(f"artifact semantic hash mismatch: {relative}")
        dependencies = artifact.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(
            isinstance(dependency, str) for dependency in dependencies
        ):
            errors.append(f"artifact dependencies must be strings: {relative}")
            continue
        for dependency in dependencies:
            if dependency not in artifact_path_set:
                errors.append(f"artifact dependency missing: {relative} -> {dependency}")
    expected_raw = semantic_hash(
        {
            row["path"]: row["sha256"]
            for row in artifacts
            if isinstance(row, dict)
            and isinstance(row.get("path"), str)
            and isinstance(row.get("sha256"), str)
        }
    )
    expected_semantic = semantic_hash(
        {
            row["path"]: row["semantic_hash"]
            for row in artifacts
            if isinstance(row, dict)
            and isinstance(row.get("path"), str)
            and isinstance(row.get("semantic_hash"), str)
        }
    )
    if manifest.get("raw_release_hash") != expected_raw:
        errors.append("raw release hash mismatch")
    if manifest.get("semantic_release_hash") != expected_semantic:
        errors.append("semantic release hash mismatch")
    if manifest.get("dependency_graph_hash") != semantic_hash(manifest.get("dependency_graph")):
        errors.append("dependency graph hash mismatch")
    if sha256_file(acceptance_path) != manifest.get("acceptance_report_hash"):
        errors.append("acceptance report hash mismatch")
    if marker.get("release_id") != manifest.get("release_id"):
        errors.append("committed marker release ID mismatch")
    if marker.get("release_manifest_hash") != sha256_file(manifest_path):
        errors.append("committed marker manifest hash mismatch")
    if manifest.get("verified") is not True:
        errors.append("release manifest is not verified")
    if acceptance.get("system_acceptance_passed") is not True:
        errors.append("system acceptance did not pass")
    if acceptance.get("release_id") != manifest.get("release_id"):
        errors.append("acceptance release ID mismatch")
    if marker.get("committed") is not True:
        errors.append("release committed marker is false")
    if acceptance.get("reproducibility") != manifest.get("reproducibility"):
        errors.append("acceptance reproducibility mismatch")
    if manifest.get("reproducibility", {}).get("verified") is not True:
        errors.append("release reproducibility is not verified")
    if acceptance.get("required_gates") != list(REQUIRED_ACCEPTANCE_GATES):
        errors.append("acceptance required gate list mismatch")
    for gate in REQUIRED_ACCEPTANCE_GATES:
        if acceptance.get(gate, {}).get("verified") is not True:
            errors.append(f"acceptance gate failed: {gate}")
    if acceptance.get("execution_integrity", {}).get(
        "nonblocking_when_not_ready"
    ) is not True:
        errors.append("execution non-ready evidence is incomplete")
    if acceptance.get("shadow_integrity", {}).get("production_approved") is not False:
        errors.append("Shadow production boundary is invalid")
    return {"available": True, "verified": not errors, "errors": errors, "manifest": manifest, "acceptance": acceptance}


def recover_release(*, root: Path = ROOT, output_dir: str = "reports/release") -> dict:
    release_root = root / output_dir
    current = release_root / "current"
    previous = release_root / "previous"
    current_status = verify_release_directory(current) if current.exists() else {"verified": False}
    if current_status.get("verified"):
        return {"recovered": False, "status": "current release is valid"}
    previous_status = verify_release_directory(previous) if previous.exists() else {"verified": False}
    if not previous_status.get("verified"):
        return {"recovered": False, "status": "no valid previous release available"}
    damaged = release_root / "damaged-current"
    if damaged.exists():
        shutil.rmtree(damaged)
    if current.exists():
        os.replace(current, damaged)
    os.replace(previous, current)
    return {"recovered": True, "status": "previous release restored"}


def clean_staging(*, root: Path = ROOT, keep_failed: bool = True) -> dict:
    staging_root = root / "reports" / ".release-staging"
    removed: list[str] = []
    retained: list[str] = []
    if not staging_root.exists():
        return {"removed": removed, "retained": retained}
    for child in sorted(staging_root.iterdir()):
        if not child.is_dir():
            continue
        if keep_failed and (child / "failure.json").exists():
            retained.append(child.name)
            continue
        shutil.rmtree(child)
        removed.append(child.name)
    return {"removed": removed, "retained": retained}


def _build_base_candidate(
    directory: Path,
    root: Path,
    config: ReleaseBuildConfig,
) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    counterfactual = load_counterfactual_report(COUNTER)
    if not counterfactual.get("available") or counterfactual.get("status") != "current" or not counterfactual.get("input_contract_verification", {}).get("verified"):
        raise ReleaseBuildError("counterfactual audit artifact is unavailable or stale", counterfactual.get("input_contract_verification", {}).get("errors", []))
    for name in COPIED_REPORTS:
        shutil.copyfile(root / "reports" / name, directory / name)

    diagnosis = read_json(root / "reports" / "strategy_diagnosis_report.json")
    v11 = build_v11_current_allocation_snapshot(
        diagnosis,
        market_data_as_of=config.market_data_as_of,
        generated_at=config.generated_at,
        diagnosis_report_path=root / "reports" / "strategy_diagnosis_report.json",
    )
    verification = validate_v11_current_allocation_snapshot(
        v11, diagnosis, verify_source_files=True
    )
    v11["source_integrity"] = verification["source_integrity"]
    v11["release_artifact_dependency"] = "v11_current_allocation.json"
    write_json(directory / "v11_current_allocation.json", v11)

    sources = load_current_market_sources(
        v11_allocation=v11,
        v11_source_path=directory / "v11_current_allocation.json",
    )
    current = build_current_market_decision(
        sources=sources,
        market_data_as_of=config.market_data_as_of,
        decision_date=config.decision_date,
        generated_at=config.generated_at,
    )
    current["release_dependencies"] = {
        "v11_current_allocation": {
            "path": "v11_current_allocation.json",
            "sha256": sha256_file(directory / "v11_current_allocation.json"),
            "snapshot_payload_hash": v11["source_integrity"][
                "snapshot_payload_hash"
            ],
            "declared": True,
        }
    }
    write_json(directory / "current_market_decision.json", current)

    actual_routes = scan_backend_web_routes(root)
    route_inventory = build_route_inventory(actual_routes)
    cleanup = build_legacy_cleanup_report(root, route_inventory)
    write_json(directory / "ui_route_inventory.json", route_inventory)
    write_json(directory / "legacy_cleanup_report.json", cleanup)

    return {
        "diagnosis": diagnosis,
        "v11": v11,
        "current": current,
        "shadow": read_json(
            root / "reports" / "execution_aware_shadow_portfolio.json"
        ),
        "route_inventory": route_inventory,
        "cleanup": cleanup,
    }


def _finalize_candidate(
    directory: Path,
    root: Path,
    config: ReleaseBuildConfig,
    release_id: str,
    inputs: list[dict],
    reproducibility: dict,
    base: dict,
) -> dict:

    protected = _protected_file_status(root)
    web_contract = validate_web_contract(root, base["route_inventory"])
    acceptance = _system_acceptance(
        root=root,
        config=config,
        release_id=release_id,
        inputs=inputs,
        diagnosis=base["diagnosis"],
        v11=base["v11"],
        current=base["current"],
        shadow=base["shadow"],
        protected=protected,
        reproducibility=reproducibility,
        web_contract=web_contract,
        route_inventory=base["route_inventory"],
        cleanup=base["cleanup"],
        staged_v11_hash=sha256_file(directory / "v11_current_allocation.json"),
    )
    write_json(directory / "system_acceptance_report.json", acceptance)

    artifacts = _artifact_rows(directory, config)
    manifest = _release_manifest(
        config=config,
        release_id=release_id,
        inputs=inputs,
        artifacts=artifacts,
        protected=protected,
        reproducibility=reproducibility,
        acceptance=acceptance,
        acceptance_hash=sha256_file(directory / "system_acceptance_report.json"),
    )
    write_json(directory / "release_manifest.json", manifest)
    write_json(
        directory / "COMMITTED.json",
        {
            "release_id": release_id,
            "committed": True,
            "generated_at": config.generated_at,
            "release_manifest_hash": sha256_file(directory / "release_manifest.json"),
        },
    )
    if not acceptance["system_acceptance_passed"]:
        raise ReleaseBuildError("system acceptance failed", acceptance["blocking_errors"])
    return {
        "release_id": release_id,
        "commit_sha": config.commit_sha,
        "input_count": len(inputs),
        "artifact_count": len(artifacts),
        "raw_release_hash": manifest["raw_release_hash"],
        "semantic_release_hash": manifest["semantic_release_hash"],
        "system_acceptance_passed": True,
        "project_completion_candidate": True,
        "dependency_graph": manifest["dependency_graph"],
    }


def _preflight_inputs(root: Path, config: ReleaseBuildConfig) -> tuple[list[dict], list[str]]:
    inputs: list[dict] = []
    errors = validate_temporal_contract(config.market_data_as_of, config.decision_date)
    for definition in LOCAL_INPUTS:
        path = root / definition.path
        if not path.exists():
            errors.append(f"required local input missing: {definition.path}")
            continue
        try:
            if path.suffix == ".json":
                value = json.loads(path.read_text(encoding="utf-8"))
                semantic = semantic_hash(value)
            else:
                semantic = None
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            errors.append(f"required local input invalid: {definition.path}")
            continue
        inputs.append(
            {
                "path": definition.path,
                "role": definition.role,
                "sha256": sha256_file(path),
                "semantic_hash": semantic,
                "source_as_of": definition.source_as_of,
                "classification": definition.classification,
                "dependencies": [],
            }
        )
    alias = validate_alias_registry(root / "data" / "universe" / "execution_instrument_aliases.json")
    errors.extend(alias["errors"])
    return inputs, list(dict.fromkeys(errors))


def _system_acceptance(**context) -> dict:
    root: Path = context["root"]
    config: ReleaseBuildConfig = context["config"]
    v11 = context["v11"]
    current = context["current"]
    shadow = context["shadow"]
    protected = context["protected"]
    diagnosis = context["diagnosis"]
    v11_validation = validate_v11_current_allocation_snapshot(v11, diagnosis, verify_source_files=True)
    execution = current.get("execution_validation", {})
    approval = validate_approval_integrity()
    identifier = current.get("comparison", {})
    dependency = current.get("release_dependencies", {}).get(
        "v11_current_allocation", {}
    )
    manifest_v11 = current.get("source_manifest", {}).get(
        "v11_current_allocation", {}
    )
    candidate = current.get("production_candidate", {})
    staged_dependency = {
        "verified": dependency.get("declared") is True
        and dependency.get("path") == "v11_current_allocation.json"
        and dependency.get("sha256") == context["staged_v11_hash"]
        and manifest_v11.get("sha256") == context["staged_v11_hash"]
        and manifest_v11.get("release_artifact_path")
        == "v11_current_allocation.json"
        and dependency.get("snapshot_payload_hash")
        == v11.get("source_integrity", {}).get("snapshot_payload_hash")
        and candidate.get("allocation") == v11.get("allocation")
        and candidate.get("allocation_integrity", {}).get("snapshot_payload_hash")
        == v11.get("source_integrity", {}).get("snapshot_payload_hash")
        and candidate.get("release_artifact_dependency")
        == "v11_current_allocation.json",
        "artifact_path": dependency.get("path"),
        "staged_v11_hash": context["staged_v11_hash"],
        "current_decision_v11_hash": manifest_v11.get("sha256"),
        "payload_hash": dependency.get("snapshot_payload_hash"),
        "root_v11_excluded": bool(
            current.get("source_hash_verification", {}).get("valid")
            and manifest_v11.get("release_artifact_path")
        ),
    }
    forbidden = (
        forbidden_field_paths(v11)
        + forbidden_field_paths(current)
        + forbidden_field_paths(shadow)
    )
    docs = [
        "README.md",
        "docs/ARCHITECTURE.md",
        "docs/OFFLINE_BUILD.md",
        "docs/OPERATIONS.md",
        "docs/DATA_CONTRACTS.md",
        "docs/LIMITATIONS.md",
    ]
    documentation = {
        "verified": all((root / path).exists() for path in docs),
        "files": docs,
        "missing": [path for path in docs if not (root / path).exists()],
    }
    checks = {
        "data_integrity": {
            "verified": len(context["inputs"]) == len(LOCAL_INPUTS),
            "input_count": len(context["inputs"]),
        },
        "strategy_integrity": {
            "verified": diagnosis.get("diagnosis", {}).get("production_readiness", {}).get("candidate") == "V11_PRODUCTION_FUSION"
        },
        "v11_snapshot_integrity": {
            "verified": v11_validation.get("valid") is True,
            "semantic_verified": v11_validation.get("source_integrity", {}).get("semantic_verified") is True,
            "errors": v11_validation.get("errors", []),
        },
        "execution_integrity": {
            "verified": execution.get("evidence_complete") is True,
            "execution_validation_ready": execution.get("ready") is True,
            "reasons": execution.get("reasons", []),
            "nonblocking_when_not_ready": execution.get("ready") is False and bool(execution.get("reasons")),
        },
        "mapping_governance_integrity": {
            "verified": all(approval.get(field) is True for field in ("approval_record_verified", "package_verified", "mapping_verified", "ledger_verified", "seal_verified")),
            "errors": approval.get("errors", []),
        },
        "shadow_integrity": {
            "verified": shadow.get("available") is True and shadow.get("snapshot_integrity", {}).get("verified") is True,
            "production_approved": shadow.get("production_approved") is True,
        },
        "current_decision_integrity": {
            "verified": current.get("ready_for_user_review") is True
            and staged_dependency["verified"],
            "status": current.get("status"),
            "staged_v11_dependency": staged_dependency,
        },
        "identifier_integrity": {
            "verified": identifier.get("identifier_normalization_verified") is True,
            "unresolved_ids": identifier.get("unresolved_instrument_ids", []),
        },
        "temporal_integrity": {
            "verified": current.get("data_freshness", {}).get("temporal_status") == "pass",
            "market_data_as_of": config.market_data_as_of,
            "decision_date": config.decision_date,
        },
        "reproducibility": context["reproducibility"],
        "production_boundary": {
            "verified": current.get("production_actionable") is False
            and current.get("comparison", {}).get("merged_portfolio_created") is False
            and current.get("comparison", {}).get("v11_vs_research_shadow", {}).get("automatic_selection") is False
            and not forbidden,
            "v11_candidate": True,
            "shadow_production_approved": False,
            "execution_validation_ready": execution.get("ready") is True,
            "production_actionable": False,
            "trading_instruction": False,
            "forbidden_field_paths": forbidden,
        },
        "api_web_contract": {
            **context["web_contract"],
            "read_only_release_apis": ["/api/system/release-manifest", "/api/system/acceptance"],
            "primary_pages": context["web_contract"].get(
                "primary_navigation", []
            ),
        },
        "ui_information_architecture": {
            "verified": context["route_inventory"].get("verified") is True
            and context["route_inventory"].get("primary_navigation_count") == 5
            and not context["route_inventory"].get("unclassified_routes"),
            "route_scan_count": context["route_inventory"].get(
                "actual_route_count", 0
            ),
            "unclassified_routes": context["route_inventory"].get(
                "unclassified_routes", []
            ),
        },
        "legacy_cleanup": context["cleanup"],
        "documentation": documentation,
        "protected_files": protected,
    }
    required_gate_names = list(REQUIRED_ACCEPTANCE_GATES)
    required = [checks[name].get("verified") is True for name in required_gate_names]
    required.extend(
        [
            checks["execution_integrity"]["nonblocking_when_not_ready"],
            checks["shadow_integrity"]["production_approved"] is False,
        ]
    )
    blocking = [
        f"{name} verification failed"
        for name in required_gate_names
        if checks[name].get("verified") is not True
    ]
    if not checks["execution_integrity"]["nonblocking_when_not_ready"]:
        blocking.append("execution non-ready evidence is incomplete")
    if checks["shadow_integrity"]["production_approved"] is not False:
        blocking.append("Shadow production boundary is invalid")
    passed = all(required) and not blocking
    return {
        "available": True,
        "release_id": context["release_id"],
        "generated_at": config.generated_at,
        "system_acceptance_passed": passed,
        "project_completion_candidate": passed,
        "required_gates": required_gate_names,
        **checks,
        "known_nonblocking_conditions": [
            "Execution Validation remains false because coverage and untradable-month thresholds are not met.",
            "Current Decision is for user review and is not production actionable.",
            "The existing Starlette/httpx deprecation warning remains.",
        ],
        "blocking_errors": blocking,
    }


def _artifact_rows(directory: Path, config: ReleaseBuildConfig) -> list[dict]:
    roles = {
        "strategy_diagnosis_report.json": ("strategy diagnosis snapshot", "verified_external_local_input", []),
        "research_backtest_report.json": ("research validation snapshot", "verified_external_local_input", []),
        "execution_backtest_report.json": ("execution validation snapshot", "verified_external_local_input", ["research_backtest_report.json"]),
        "execution_aware_shadow_portfolio.json": ("shadow portfolio snapshot", "verified_external_local_input", ["research_backtest_report.json", "execution_backtest_report.json"]),
        "execution_mapping_counterfactual_report.json": ("counterfactual mapping audit", "verified_external_local_input", ["research_backtest_report.json", "execution_backtest_report.json"]),
        "v11_current_allocation.json": ("V11 current allocation", "rebuilt_artifact", ["strategy_diagnosis_report.json"]),
        "current_market_decision.json": ("current market decision", "rebuilt_artifact", ["v11_current_allocation.json", "execution_aware_shadow_portfolio.json"]),
        "ui_route_inventory.json": ("final UI route inventory", "rebuilt_artifact", []),
        "legacy_cleanup_report.json": ("legacy UI cleanup evidence", "rebuilt_artifact", ["ui_route_inventory.json"]),
        "system_acceptance_report.json": ("system acceptance", "rebuilt_artifact", ["current_market_decision.json"]),
    }
    rows: list[dict] = []
    for name, (role, classification, dependencies) in roles.items():
        path = directory / name
        value = read_json(path)
        rows.append({
            "path": name,
            "role": role,
            "sha256": sha256_file(path),
            "semantic_hash": semantic_hash(value),
            "source_as_of": config.market_data_as_of,
            "classification": classification,
            "dependencies": dependencies,
        })
    return rows


def _release_manifest(**context) -> dict:
    config: ReleaseBuildConfig = context["config"]
    artifacts = context["artifacts"]
    raw_release_hash = semantic_hash({row["path"]: row["sha256"] for row in artifacts})
    semantic_release_hash = semantic_hash({row["path"]: row["semantic_hash"] for row in artifacts})
    acceptance = context["acceptance"]
    return {
        "available": True,
        "release_id": context["release_id"],
        "commit_sha": config.commit_sha,
        "market_data_as_of": config.market_data_as_of,
        "decision_date": config.decision_date,
        "generated_at": config.generated_at,
        "build_mode": "offline_local",
        "network_accessed": False,
        "inputs": context["inputs"],
        "artifacts": artifacts,
        "dependency_graph": dependency_graph(),
        "dependency_graph_hash": dependency_graph_hash(),
        "protected_file_hashes": context["protected"],
        "reproducibility": context["reproducibility"],
        "acceptance_report_hash": context["acceptance_hash"],
        "raw_release_hash": raw_release_hash,
        "semantic_release_hash": semantic_release_hash,
        "production_boundary": acceptance["production_boundary"],
        "verified": acceptance["system_acceptance_passed"] is True,
        "errors": acceptance["blocking_errors"],
    }


def _protected_file_status(root: Path) -> dict:
    files: list[dict] = []
    errors: list[str] = []
    for path, expected in PROTECTED_FILE_HASHES.items():
        source = root / path
        actual = sha256_file(source) if source.exists() else None
        verified = actual == expected
        files.append({"path": path, "baseline_sha256": expected, "actual_sha256": actual, "verified": verified})
        if not verified:
            errors.append(f"protected file drift: {path}")
    return {"baseline_commit": PROTECTED_BASELINE_COMMIT, "verified": not errors, "files": files, "errors": errors}


def _directory_hash_differences(first: Path, second: Path) -> list[dict]:
    first_files = {path.relative_to(first).as_posix(): sha256_file(path) for path in first.rglob("*") if path.is_file()}
    second_files = {path.relative_to(second).as_posix(): sha256_file(path) for path in second.rglob("*") if path.is_file()}
    return [
        {"path": path, "first_sha256": first_files.get(path), "second_sha256": second_files.get(path)}
        for path in sorted(set(first_files) | set(second_files))
        if first_files.get(path) != second_files.get(path)
    ]


def _candidate_content_hashes(directory: Path) -> tuple[str, str]:
    files = sorted(path for path in directory.rglob("*.json") if path.is_file())
    raw = {
        path.relative_to(directory).as_posix(): sha256_file(path) for path in files
    }
    semantic = {
        path.relative_to(directory).as_posix(): semantic_hash(read_json(path))
        for path in files
    }
    return semantic_hash(raw), semantic_hash(semantic)


def _promote_release(candidate: Path, release_root: Path, release_id: str) -> None:
    status = verify_release_directory(candidate)
    if not status.get("verified"):
        raise ReleaseBuildError("candidate release integrity failed", status.get("errors", []))
    current = release_root / "current"
    previous = release_root / "previous"
    if previous.exists():
        shutil.rmtree(previous)
    if current.exists():
        os.replace(current, previous)
    try:
        os.replace(candidate, current)
    except Exception:
        if not current.exists() and previous.exists():
            os.replace(previous, current)
        raise


@contextmanager
def _exclusive_lock(path: Path):
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        yield
    except FileExistsError as exc:
        raise ReleaseBuildError("another release build holds the exclusive lock", [str(path)]) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
            path.unlink(missing_ok=True)


class ReleaseBuildError(RuntimeError):
    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or []
