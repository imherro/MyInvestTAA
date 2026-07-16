from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from current_taa.drawdown_events import (
    DrawdownInputError,
    analyze_drawdown_history,
)
from scripts.build_a_tier_drawdown_events import (
    DrawdownBuildError,
    build_drawdown_report_set,
    publish_drawdown_report_set,
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


def _row(row_date: str, close: float, *, basis: str = "total_return") -> dict:
    return {"date": row_date, "close": close, "return_basis": basis}


def test_monotonic_history_has_no_event_and_high_watermark_states() -> None:
    result = analyze_drawdown_history(_rows(100, 101, 102), asset_key="asset")

    assert result.events == ()
    assert [point.state for point in result.drawdown_series] == [
        "high_watermark",
        "high_watermark",
        "high_watermark",
    ]
    assert result.current_state["drawdown"] == 0.0
    assert result.current_state["event_id"] is None


def test_completed_event_preserves_first_equal_trough_and_durations() -> None:
    result = analyze_drawdown_history(
        _rows(100, 90, 80, 80, 100), asset_key="asset"
    )
    event = result.events[0]

    assert event.event_id == "asset:2020-01-01"
    assert event.completed is True
    assert event.start_date == "2020-01-02"
    assert event.trough_date == "2020-01-03"
    assert event.recovery_date == "2020-01-05"
    assert event.max_drawdown == pytest.approx(-0.2)
    assert event.decline_sessions == 2
    assert event.recovery_sessions == 2
    assert event.event_span_sessions == 4
    assert event.underwater_observations == 3
    assert result.drawdown_series[-1].state == "recovered"
    assert result.drawdown_series[-1].event_id == event.event_id


def test_open_event_updates_trough_without_creating_multiple_events() -> None:
    result = analyze_drawdown_history(
        _rows(100, 95, 90, 92, 80, 85), asset_key="asset"
    )
    event = result.events[0]

    assert len(result.events) == 1
    assert event.completed is False
    assert event.trough_date == "2020-01-05"
    assert event.recovery_date is None
    assert event.recovery_sessions is None
    assert event.last_observation_date == "2020-01-06"
    assert event.event_span_sessions == 5
    assert result.current_state["open_event"]["event_id"] == event.event_id


def test_equal_high_uses_recent_date_and_recovery_can_start_later_event() -> None:
    result = analyze_drawdown_history(
        _rows(100, 100, 90, 105, 100), asset_key="asset"
    )

    assert [event.event_id for event in result.events] == [
        "asset:2020-01-02",
        "asset:2020-01-04",
    ]
    assert result.events[0].completed is True
    assert result.events[0].recovery_date == "2020-01-04"
    assert result.events[1].completed is False
    assert result.drawdown_series[3].state == "recovered"


def test_exact_peak_and_overshoot_both_recover_one_event() -> None:
    exact = analyze_drawdown_history(_rows(100, 90, 100), asset_key="exact")
    overshoot = analyze_drawdown_history(_rows(100, 90, 110), asset_key="over")

    assert len(exact.events) == len(overshoot.events) == 1
    assert exact.events[0].completed is overshoot.events[0].completed is True
    assert overshoot.drawdown_series[-1].high_watermark == 110
    assert overshoot.drawdown_series[-1].state == "recovered"


def test_as_of_is_prefix_equivalent_and_future_invariant() -> None:
    full = _rows(100, 90, 80, 100, 70)
    as_of = analyze_drawdown_history(
        full, asset_key="asset", as_of_date="2020-01-03"
    )
    prefix = analyze_drawdown_history(full[:3], asset_key="asset")
    appended = analyze_drawdown_history(
        full + _rows_from("2020-01-06", 120, 60),
        asset_key="asset",
        as_of_date="2020-01-03",
    )

    assert as_of == prefix == appended
    assert as_of.events[0].completed is False
    assert as_of.events[0].trough_value == 80
    assert as_of.events[0].recovery_date is None


@pytest.mark.parametrize(
    "as_of_date", ["2019-12-31", "2020-01-02", "2020-01-04"]
)
def test_as_of_must_be_an_actual_input_date(as_of_date: str) -> None:
    with pytest.raises(DrawdownInputError, match="actual input trading date"):
        analyze_drawdown_history(
            [_row("2020-01-01", 100), _row("2020-01-03", 90)],
            asset_key="asset",
            as_of_date=as_of_date,
        )


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([_row("2020-01-01", 100), _row("2020-01-01", 90)], "strictly increasing"),
        ([_row("2020-01-02", 100), _row("2020-01-01", 90)], "strictly increasing"),
        ([_row("2020-01-01", 0)], "finite positive"),
        ([_row("2020-01-01", float("nan"))], "finite positive"),
        ([_row("2020-01-01", float("inf"))], "finite positive"),
        ([_row("2020-01-01", True)], "malformed"),
        ([_row("2020-01-01", 100, basis="price")], "total_return"),
        ([_row("20200101", 100)], "YYYY-MM-DD"),
        ([_row("not-a-date", 100)], "YYYY-MM-DD"),
    ],
)
def test_invalid_price_history_fails_closed(rows: list[dict], message: str) -> None:
    with pytest.raises(DrawdownInputError, match=message):
        analyze_drawdown_history(rows, asset_key="asset")


def test_builder_generates_five_analyzed_two_blocked_and_source_hashes(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    reports = build_drawdown_report_set(
        project, generated_at="2026-07-16T00:00:00+00:00"
    )
    index = reports["index.json"]

    assert set(reports) == {"index.json"} | {
        f"{asset_key}.json" for asset_key in TIER_A_KEYS
    }
    assert index["summary"]["analyzed_assets"] == 5
    assert index["summary"]["blocked_assets"] == 2
    assert index["summary"]["completed_events"] == 5
    assert [row["asset_key"] for row in index["assets"]] == TIER_A_KEYS
    audit_bytes = (project / "reports/strategy_research/universe_audit.json").read_bytes()
    assert index["source_audit_sha256"] == hashlib.sha256(audit_bytes).hexdigest()
    for asset_key in ANALYZED_KEYS:
        report = reports[f"{asset_key}.json"]
        cache = project / report["source_cache_path"]
        assert report["analysis_status"] == "analyzed"
        assert report["source_cache_sha256"] == hashlib.sha256(
            cache.read_bytes()
        ).hexdigest()
    for asset_key in set(TIER_A_KEYS) - ANALYZED_KEYS:
        report = reports[f"{asset_key}.json"]
        assert report["analysis_status"] == "blocked"
        assert report["source_cache_path"] is None
        assert report["events"] == report["drawdown_series"] == []
        assert report["current_state"] is None


def test_builder_is_deterministic_except_index_timestamp_and_has_no_secrets(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    first = build_drawdown_report_set(project, generated_at="first")
    second = build_drawdown_report_set(project, generated_at="second")
    first["index.json"].pop("generated_at")
    second["index.json"].pop("generated_at")

    assert first == second
    text = json.dumps(first, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text
    assert "token" not in text.lower()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda audit: audit.update(universe_hash="bad"), "universe_hash"),
        (lambda audit: audit.update(universe_id="bad"), "universe_id"),
        (lambda audit: audit["assets"].pop(), "exactly tier A"),
        (lambda audit: audit["assets"].append(copy.deepcopy(audit["assets"][0])), "duplicate"),
        (
            lambda audit: audit["assets"][0].update(asset_key="unknown_asset"),
            "exactly tier A",
        ),
        (lambda audit: audit["assets"][0].update(provider_code="wrong"), "contract fields"),
        (
            lambda audit: audit["assets"][0].update(
                contract_research_status="blocked"
            ),
            "contract fields",
        ),
    ],
)
def test_builder_rejects_stale_or_inconsistent_audit(
    tmp_path: Path, mutation, message: str
) -> None:
    project = _project_fixture(tmp_path)
    path = project / "reports/strategy_research/universe_audit.json"
    audit = json.loads(path.read_text(encoding="utf-8"))
    mutation(audit)
    path.write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DrawdownBuildError, match=message):
        build_drawdown_report_set(project)


def test_blocked_assets_do_not_require_or_read_a_cache(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)
    assert not (project / "data/research_prices/399606_SZ.json").exists()

    reports = build_drawdown_report_set(project)

    assert reports["chinext_total_return.json"]["analysis_status"] == "blocked"


def test_atomic_publish_replaces_complete_directory_and_invalid_set_preserves_old(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path / "project")
    reports = build_drawdown_report_set(project, generated_at="fixed")
    target = tmp_path / "published"
    target.mkdir()
    (target / "old.json").write_text("old", encoding="utf-8")

    with pytest.raises(DrawdownBuildError):
        publish_drawdown_report_set(target, {"index.json": reports["index.json"]})
    assert (target / "old.json").read_text(encoding="utf-8") == "old"

    publish_drawdown_report_set(target, reports)
    assert {path.name for path in target.iterdir()} == set(reports)
    assert not target.with_name("published.previous").exists()


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
        cache.write_text(
            json.dumps(_rows(100, 90, 80, 100), ensure_ascii=False),
            encoding="utf-8",
        )
    return project


def _rows(*prices: float) -> list[dict]:
    return [
        _row(f"2020-01-{index:02d}", price)
        for index, price in enumerate(prices, start=1)
    ]


def _rows_from(start: str, *prices: float) -> list[dict]:
    year, month, day = (int(value) for value in start.split("-"))
    return [
        _row(f"{year:04d}-{month:02d}-{day + index:02d}", price)
        for index, price in enumerate(prices)
    ]
