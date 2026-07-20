from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "data" / "strategy_style_walk_forward_v1"


@dataclass(frozen=True)
class ProfileDecision:
    profile_id: str
    condition_a_passed: bool
    condition_b_passed: bool
    condition_c_passed: bool
    condition_d_passed: bool
    h60_median: float
    support_status: str


@dataclass(frozen=True)
class StrategyStyleResearchView:
    source_as_of_date: str
    mechanism_decision: str
    integration_status: str
    allocation_status: str
    backtest_status: str
    supported_profile_count: int
    profiles: tuple[ProfileDecision, ...]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"研究结果无法读取：{path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"研究结果格式无效：{path.name}")
    return payload


def load_strategy_style_research_view(
    artifact_dir: Path | None = None,
) -> StrategyStyleResearchView:
    root = artifact_dir or ARTIFACT_DIR
    manifest = _load_json(root / "manifest.json")
    summary = _load_json(root / "walk_forward_summary.json")

    if manifest.get("artifact_set_id") != "STRATEGY_STYLE_WALK_FORWARD_ARTIFACT_V1":
        raise ValueError("P2 研究结果身份不匹配")
    if summary.get("dataset_id") != "STRATEGY_STYLE_WALK_FORWARD_SUMMARY_V1":
        raise ValueError("P2 汇总结果身份不匹配")
    if manifest.get("mechanism_decision") != summary.get("mechanism_decision"):
        raise ValueError("P2 研究结论不一致")
    if manifest.get("mechanism_decision") != "REJECTED":
        raise ValueError("P2 研究结论不是已确认的否决状态")
    if manifest.get("selected_profile") is not None or summary.get("selected_profile") is not None:
        raise ValueError("P2 研究结果存在未声明的入选方案")

    profile_rows = summary.get("profile_decisions")
    if not isinstance(profile_rows, list) or len(profile_rows) != 3:
        raise ValueError("P2 方案结果不完整")
    profiles = tuple(
        ProfileDecision(
            profile_id=str(row["profile_id"]),
            condition_a_passed=bool(row["condition_a_passed"]),
            condition_b_passed=bool(row["condition_b_passed"]),
            condition_c_passed=bool(row["condition_c_passed"]),
            condition_d_passed=bool(row["condition_d_passed"]),
            h60_median=float(row["condition_c_median"]),
            support_status=str(row["profile_support_status"]),
        )
        for row in profile_rows
    )
    supported = summary.get("supported_profiles")
    if not isinstance(supported, list):
        raise ValueError("P2 支持方案字段无效")
    statuses = manifest.get("statuses")
    if not isinstance(statuses, dict):
        raise ValueError("P2 生命周期状态缺失")
    expected_statuses = {
        "integration_status": "DO_NOT_INTEGRATE",
        "allocation_status": "NOT_DEFINED",
        "backtest_status": "NOT_RUN",
    }
    if any(statuses.get(key) != value for key, value in expected_statuses.items()):
        raise ValueError("P2 下游禁用状态不一致")

    return StrategyStyleResearchView(
        source_as_of_date=str(manifest["source_as_of_date"]),
        mechanism_decision=str(manifest["mechanism_decision"]),
        integration_status=str(statuses["integration_status"]),
        allocation_status=str(statuses["allocation_status"]),
        backtest_status=str(statuses["backtest_status"]),
        supported_profile_count=len(supported),
        profiles=profiles,
    )
