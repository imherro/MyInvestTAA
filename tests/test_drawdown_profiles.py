from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from current_taa.drawdown_events import analyze_drawdown_history
from current_taa.drawdown_profiles import (
    DrawdownProfileError,
    build_drawdown_profile,
    linear_quantile,
)
from scripts.build_a_tier_drawdown_events import (
    build_drawdown_report_set,
    publish_drawdown_report_set,
)
from scripts.build_a_tier_drawdown_profiles import (
    DrawdownProfileBuildError,
    build_drawdown_profile_report_set,
    publish_drawdown_profile_report_set,
)


ROOT = Path(__file__).resolve().parents[1]
TIER_A_KEYS = [
    "csi300_total_return",
    "csi500_total_return",
    "csi1000_total_return",
    "chinext_total_return",
    "cni1000_value_total_return",
    "csi_dividend_total_return",
    "cni_free_cash_flow_total_return",
]
ANALYZED_KEYS = {
    "csi300_total_return",
    "csi500_total_return",
    "csi1000_total_return",
    "csi_dividend_total_return",
    "cni_free_cash_flow_total_return",
}


def test_r7_quantile_is_deterministic_and_handles_empty_samples() -> None:
    assert linear_quantile([], 0.5) is None
    assert linear_quantile([7], 0.975) == 7
    assert linear_quantile([10, 0], 0.6) == 6
    with pytest.raises(DrawdownProfileError, match="probability"):
        linear_quantile([1], 1.1)


def test_profile_separates_daily_completed_and_open_event_samples() -> None:
    profile = build_drawdown_profile(_event_report())
    daily = profile["daily_depth_profile"]
    completed = profile["event_depth_profile"]["completed_events"]
    opened = profile["event_depth_profile"]["current_open_event"]
    current = profile["current_position"]

    assert daily["all_observations"]["sample_count"] == 6
    assert daily["all_observations"]["zero_depth_count"] == 3
    assert daily["all_observations"]["underwater_rate"] == 0.5
    assert daily["underwater_observations"]["sample_count"] == 3
    assert daily["underwater_observations"]["minimum"] == 0.1
    assert completed["completed_event_count"] == 1
    assert completed["maximum"] == 0.2
    assert profile["duration_profile"]["decline_sessions"]["minimum"] == 2
    assert isinstance(
        profile["duration_profile"]["decline_sessions"]["minimum"], int
    )
    assert profile["duration_profile"]["recovery_sessions"]["mean"] == 1
    assert opened["max_depth_to_date"] == 0.1
    assert current["current_drawdown"] == -0.1
    assert current["all_observations_percentile"] == pytest.approx(5 / 6)
    assert current["all_observations_exceedance_rate"] == 0.5
    assert current["open_event_depth_position"] == {
        "completed_event_depth_percentile": 0.0,
        "completed_event_depth_exceedance_rate": 1.0,
    }


def test_blocked_profile_has_only_null_profile_sections() -> None:
    assert build_drawdown_profile({"analysis_status": "blocked"}) == {
        "daily_depth_profile": None,
        "event_depth_profile": None,
        "duration_profile": None,
        "current_position": None,
    }


def test_as_of_rebuilds_visible_facts_and_ignores_arbitrary_future_content() -> None:
    report = _event_report()
    expected = build_drawdown_profile(report, as_of_date="2020-01-03")
    changed = copy.deepcopy(report)
    changed["events"] = ["future event facts must not be read"]
    changed["drawdown_series"][3:] = [
        {"date": "not-a-date", "close": "bad", "drawdown": float("nan")}
    ]

    actual = build_drawdown_profile(changed, as_of_date="2020-01-03")

    assert actual == expected
    assert actual["event_depth_profile"]["completed_events"][
        "completed_event_count"
    ] == 0
    assert actual["event_depth_profile"]["current_open_event"][
        "max_depth_to_date"
    ] == 0.2


def test_as_of_requires_actual_date_and_valid_visible_prefix() -> None:
    report = _event_report()
    with pytest.raises(DrawdownProfileError, match="actual input trading date"):
        build_drawdown_profile(report, as_of_date="2020-01-07")
    report["drawdown_series"][1]["close"] = 0
    with pytest.raises(ValueError, match="finite positive"):
        build_drawdown_profile(report, as_of_date="2020-01-03")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report["drawdown_series"][0].update(date="20200101"),
        lambda report: report["drawdown_series"][1].update(drawdown=0),
        lambda report: report["drawdown_series"][0].update(drawdown=-0.1),
        lambda report: report["drawdown_series"][1].update(event_id=None),
        lambda report: report["events"][0].update(event_sequence=2),
        lambda report: report["events"][0].update(recovery_sessions=-1),
        lambda report: report["event_summary"].update(completed_event_count=0),
        lambda report: report["events"][0].update(underwater_observations=1),
    ],
)
def test_full_profile_fails_closed_on_inconsistent_event_facts(mutation) -> None:
    report = _event_report()
    mutation(report)
    with pytest.raises(DrawdownProfileError):
        build_drawdown_profile(report)


def test_builder_produces_exact_source_bound_report_set(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)
    reports = build_drawdown_profile_report_set(
        project, generated_at="2026-07-16T00:00:00+00:00"
    )
    index = reports["index.json"]

    assert set(reports) == {"index.json"} | {
        f"{asset_key}.json" for asset_key in TIER_A_KEYS
    }
    assert index["summary"] == {
        "tier_a_assets": 7,
        "analyzed_assets": 5,
        "blocked_assets": 2,
    }
    assert [row["asset_key"] for row in index["assets"]] == TIER_A_KEYS
    event_index = project / "reports/strategy_research/drawdown_events/index.json"
    assert index["source_event_index_sha256"] == hashlib.sha256(
        event_index.read_bytes()
    ).hexdigest()
    for row in index["assets"]:
        report = reports[f"{row['asset_key']}.json"]
        event_path = project / report["source_event_report_path"]
        assert report["source_event_report_sha256"] == hashlib.sha256(
            event_path.read_bytes()
        ).hexdigest()
        if row["asset_key"] not in ANALYZED_KEYS:
            assert report["period"] is None
            assert report["daily_depth_profile"] is None


def test_builder_rebinds_index_identity_to_current_universe(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)
    index_path = project / "reports/strategy_research/drawdown_events/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["assets"][0]["provider_code"] = "wrong.provider"
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DrawdownProfileBuildError, match="identity differs"):
        build_drawdown_profile_report_set(project)


def test_builder_rejects_stale_audit_hash(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)
    audit_path = project / "reports/strategy_research/universe_audit.json"
    audit_path.write_bytes(audit_path.read_bytes() + b"\n")

    with pytest.raises(DrawdownProfileBuildError, match="audit hash"):
        build_drawdown_profile_report_set(project)


def test_atomic_publish_preserves_old_target_then_replaces_it(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path / "project")
    reports = build_drawdown_profile_report_set(project, generated_at="fixed")
    target = tmp_path / "published"
    target.mkdir()
    (target / "old.json").write_text("old", encoding="utf-8")

    with pytest.raises(DrawdownProfileBuildError):
        publish_drawdown_profile_report_set(
            target, {"index.json": reports["index.json"]}
        )
    assert (target / "old.json").read_text(encoding="utf-8") == "old"

    publish_drawdown_profile_report_set(target, reports)
    assert {path.name for path in target.iterdir()} == set(reports)
    assert not target.with_name("published.previous").exists()


def _event_report() -> dict:
    analysis = analyze_drawdown_history(
        _rows(100, 90, 80, 100, 110, 99), asset_key="asset"
    )
    events = [event.to_dict() for event in analysis.events]
    return {
        "analysis_status": "analyzed",
        "asset": {
            "asset_key": "asset",
            "provider_code": "asset.provider",
            "risk_family": "broad_beta",
        },
        "period": {
            "first_date": analysis.first_date,
            "last_date": analysis.last_date,
            "row_count": analysis.row_count,
        },
        "event_summary": {
            "total_event_count": len(events),
            "completed_event_count": sum(event["completed"] for event in events),
            "open_event_count": sum(not event["completed"] for event in events),
        },
        "events": events,
        "drawdown_series": [point.to_dict() for point in analysis.drawdown_series],
        "current_state": analysis.current_state,
    }


def _project_fixture(tmp_path: Path) -> Path:
    project = tmp_path
    (project / "config").mkdir(parents=True)
    (project / "reports/strategy_research").mkdir(parents=True)
    (project / "data/research_prices").mkdir(parents=True)
    contract_path = project / "config/research_universe_v1.json"
    contract_path.write_bytes((ROOT / "config/research_universe_v1.json").read_bytes())
    audit_path = project / "reports/strategy_research/universe_audit.json"
    audit_path.write_bytes(
        (ROOT / "reports/strategy_research/universe_audit.json").read_bytes()
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for asset in contract["assets"][:7]:
        if asset["asset_key"] not in ANALYZED_KEYS:
            continue
        cache = (
            project
            / "data/research_prices"
            / f"{asset['provider_code'].replace('.', '_')}.json"
        )
        cache.write_text(json.dumps(_rows(100, 90, 80, 100)), encoding="utf-8")
    event_reports = build_drawdown_report_set(project, generated_at="fixed")
    publish_drawdown_report_set(
        project / "reports/strategy_research/drawdown_events", event_reports
    )
    return project


def _rows(*prices: float) -> list[dict]:
    return [
        {
            "date": f"2020-01-{index:02d}",
            "close": price,
            "return_basis": "total_return",
        }
        for index, price in enumerate(prices, start=1)
    ]
