from __future__ import annotations

import copy
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from current_taa.drawdown_events import analyze_drawdown_history
from current_taa.drawdown_outcomes import (
    DrawdownOutcomeError,
    build_drawdown_outcomes,
)
from scripts.build_a_tier_drawdown_events import (
    build_drawdown_report_set,
    publish_drawdown_report_set,
)
from scripts.build_a_tier_drawdown_outcomes import (
    DrawdownOutcomeBuildError,
    build_drawdown_outcome_report_set,
    publish_drawdown_outcome_report_set,
)


ROOT = Path(__file__).resolve().parents[1]
ANALYZED_KEYS = {
    "csi300_total_return",
    "csi500_total_return",
    "csi1000_total_return",
    "csi_dividend_total_return",
    "cni_free_cash_flow_total_return",
}


def test_frontiers_require_strict_new_lows_and_have_stable_identity() -> None:
    result = build_drawdown_outcomes(_report(100, 90, 80, 80, 85, 70, 100))
    records = result["records"]

    assert [record["trigger_close"] for record in records] == [90, 80, 70]
    assert [record["frontier_sequence"] for record in records] == [1, 2, 3]
    assert [record["record_id"] for record in records] == [
        "asset:1:1",
        "asset:1:2",
        "asset:1:3",
    ]
    assert records[0]["prior_frontier_depth"] is None
    assert records[1]["depth_increment"] > 0


def test_new_event_restarts_frontier_sequence() -> None:
    records = build_drawdown_outcomes(_report(100, 90, 100, 110, 100))["records"]

    assert [(row["event_sequence"], row["frontier_sequence"]) for row in records] == [
        (1, 1),
        (2, 1),
    ]


def test_completed_minimum_and_recovery_outcomes_are_observed() -> None:
    records = build_drawdown_outcomes(_report(100, 90, 80, 80, 100))["records"]
    first, trough = records[0], records[-1]

    assert first["minimum_outcome"] == {
        "status": "realized",
        "minimum_date": "2020-01-03",
        "minimum_close": 80.0,
        "minimum_series_index": 2,
        "additional_return_from_trigger": pytest.approx(80 / 90 - 1),
        "sessions_from_trigger": 1,
    }
    assert trough["minimum_outcome"]["additional_return_from_trigger"] == 0
    assert first["trigger_price_recovery"]["status"] == "observed"
    assert first["peak_recovery"]["status"] == "observed"


def test_open_event_can_recover_trigger_price_while_peak_remains_censored() -> None:
    record = build_drawdown_outcomes(_report(100, 80, 90))["records"][0]

    assert record["minimum_outcome"]["status"] == "censored"
    assert record["trigger_price_recovery"]["status"] == "observed"
    assert record["peak_recovery"]["status"] == "censored"


def test_fixed_horizons_use_exact_session_indexes_and_full_path() -> None:
    prices = [100, 90] + [100 + index for index in range(800)]
    record = build_drawdown_outcomes(_report(*prices))["records"][0]
    horizons = {row["horizon_sessions"]: row for row in record["horizons"]}

    assert set(horizons) == {63, 126, 252, 504, 756}
    for sessions, outcome in horizons.items():
        assert outcome["status"] == "observed"
        assert outcome["end_date"] == _rows(*prices)[1 + sessions]["date"]
        assert outcome["maximum_adverse_excursion"] <= 0
        assert outcome["maximum_favorable_excursion"] >= 0


def test_incomplete_horizons_are_entirely_censored() -> None:
    record = build_drawdown_outcomes(_report(100, 90, 100))["records"][0]

    for outcome in record["horizons"]:
        assert outcome["status"] == "censored"
        assert all(
            outcome[field] is None
            for field in (
                "end_date",
                "end_close",
                "forward_return",
                "maximum_adverse_excursion",
                "maximum_favorable_excursion",
            )
        )


def test_as_of_is_prefix_equivalent_and_ignores_malformed_future_facts() -> None:
    report = _report(100, 90, 80, 100, 110)
    expected = build_drawdown_outcomes(report, as_of_date="2020-01-03")
    changed = copy.deepcopy(report)
    changed["events"] = ["future"]
    changed["current_state"] = "future"
    changed["drawdown_series"][3:] = [{"date": "bad", "close": "bad"}]

    assert build_drawdown_outcomes(changed, as_of_date="2020-01-03") == expected
    assert expected["records"][-1]["peak_recovery"]["status"] == "censored"
    assert all(
        horizon["status"] == "censored"
        for horizon in expected["records"][0]["horizons"]
    )


def test_as_of_requires_actual_date_and_valid_visible_prefix() -> None:
    report = _report(100, 90, 80)
    with pytest.raises(DrawdownOutcomeError, match="actual input trading date"):
        build_drawdown_outcomes(report, as_of_date="2020-01-04")
    report["drawdown_series"][1]["close"] = 0
    with pytest.raises(ValueError, match="finite positive"):
        build_drawdown_outcomes(report, as_of_date="2020-01-03")


def test_builder_generates_five_analyzed_two_blocked_and_exact_files(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    reports = build_drawdown_outcome_report_set(project, generated_at="fixed")

    assert len(reports) == 8
    assert reports["index.json"]["summary"]["analyzed_assets"] == 5
    assert reports["index.json"]["summary"]["blocked_assets"] == 2
    for key in {"chinext_total_return", "cni1000_value_total_return"}:
        assert reports[f"{key}.json"]["records"] == []


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_builder_rejects_open_event_source_json_set(
    tmp_path: Path, change: str
) -> None:
    project = _project_fixture(tmp_path)
    event_dir = project / "reports/strategy_research/drawdown_events"
    if change == "missing":
        (event_dir / "csi300_total_return.json").unlink()
    else:
        (event_dir / "unknown.json").write_text("{}", encoding="utf-8")
    with pytest.raises(DrawdownOutcomeBuildError):
        build_drawdown_outcome_report_set(project)


def test_builder_is_deterministic_safe_and_atomic(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path / "project")
    first = build_drawdown_outcome_report_set(project, generated_at="first")
    second = build_drawdown_outcome_report_set(project, generated_at="second")
    first["index.json"].pop("generated_at")
    second["index.json"].pop("generated_at")
    assert first == second
    text = json.dumps(first, allow_nan=False).lower()
    assert "infinity" not in text and "token" not in text

    target = tmp_path / "published"
    target.mkdir()
    (target / "old.json").write_text("old", encoding="utf-8")
    with pytest.raises(DrawdownOutcomeBuildError):
        publish_drawdown_outcome_report_set(target, {"index.json": {}})
    assert (target / "old.json").exists()
    publish_drawdown_outcome_report_set(
        target, first | {"index.json": second["index.json"]}
    )
    assert len(list(target.glob("*.json"))) == 8


def _report(*prices: float) -> dict:
    analysis = analyze_drawdown_history(_rows(*prices), asset_key="asset")
    events = [event.to_dict() for event in analysis.events]
    return {
        "analysis_status": "analyzed",
        "asset": {
            "asset_key": "asset",
            "provider_code": "p",
            "risk_family": "broad_beta",
        },
        "period": {
            "first_date": analysis.first_date,
            "last_date": analysis.last_date,
            "row_count": analysis.row_count,
        },
        "event_summary": {
            "total_event_count": len(events),
            "completed_event_count": sum(e["completed"] for e in events),
            "open_event_count": sum(not e["completed"] for e in events),
        },
        "events": events,
        "drawdown_series": [point.to_dict() for point in analysis.drawdown_series],
        "current_state": analysis.current_state,
    }


def _project_fixture(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "reports/strategy_research").mkdir(parents=True)
    (tmp_path / "data/research_prices").mkdir(parents=True)
    (tmp_path / "config/research_universe_v1.json").write_bytes(
        (ROOT / "config/research_universe_v1.json").read_bytes()
    )
    (tmp_path / "reports/strategy_research/universe_audit.json").write_bytes(
        (ROOT / "reports/strategy_research/universe_audit.json").read_bytes()
    )
    contract = json.loads(
        (tmp_path / "config/research_universe_v1.json").read_text(encoding="utf-8")
    )
    for asset in contract["assets"][:7]:
        if asset["asset_key"] in ANALYZED_KEYS:
            path = (
                tmp_path
                / "data/research_prices"
                / f"{asset['provider_code'].replace('.', '_')}.json"
            )
            path.write_text(json.dumps(_rows(100, 90, 80, 100)), encoding="utf-8")
    events = build_drawdown_report_set(tmp_path, generated_at="fixed")
    publish_drawdown_report_set(
        tmp_path / "reports/strategy_research/drawdown_events", events
    )
    return tmp_path


def _rows(*prices: float) -> list[dict]:
    start = date(2020, 1, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "close": price,
            "return_basis": "total_return",
        }
        for index, price in enumerate(prices)
    ]
