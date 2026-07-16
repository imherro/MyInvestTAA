from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_strategy_style_research_dataset import (  # noqa: E402
    DATASET_RELATIVE,
    REPORT_RELATIVE,
    UNIVERSE_RELATIVE,
    AssetSnapshot,
    StrategyStyleDatasetError,
    build_strategy_style_research_dataset,
    qualify_asset,
    validate_index_basic,
    validate_price_rows,
    validate_universe_config,
    year_chunks,
)


AS_OF = "2026-07-15"
FAKE_DATES = ("2026-07-13", "2026-07-14", "2026-07-15")


def _universe() -> dict:
    return json.loads((ROOT / UNIVERSE_RELATIVE).read_text(encoding="utf-8"))


class FakeProvider:
    def __init__(self, universe: dict | None = None) -> None:
        source = universe or _universe()
        self.assets = {asset["asset_id"]: asset for asset in source["assets"]}
        self.daily_calls: list[tuple[str, str, str]] = []
        self.calendar_calls: list[tuple[str, str]] = []
        self.duplicate_asset: str | None = None
        self.empty_asset: str | None = None
        self.fail_asset: str | None = None
        self.price_override: dict[str, object] = {}
        self.calendar_dates = list(FAKE_DATES)

    def index_basic(self, *, ts_code: str, fields: str) -> list[dict]:
        if ts_code == self.fail_asset:
            raise RuntimeError("simulated download failure")
        asset = self.assets[ts_code]
        expected = asset.get("expected_index_basic") or {
            "name": asset["display_name"],
            "fullname": f"{asset['display_name']}全收益指数",
            "market": ts_code.split(".")[-1],
            "category": "策略指数",
            "base_date": "20121231",
            "list_date": "20130104",
        }
        return [{"ts_code": ts_code, **expected}]

    def index_daily(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
        fields: str,
    ) -> list[dict]:
        self.daily_calls.append((ts_code, start_date, end_date))
        if ts_code == self.empty_asset:
            return []
        rows = [
            {
                "ts_code": ts_code,
                "trade_date": date.replace("-", ""),
                "close": self.price_override.get(date, 100.0 + index),
            }
            for index, date in enumerate(FAKE_DATES)
            if start_date <= date.replace("-", "") <= end_date
        ]
        if ts_code == self.duplicate_asset and start_date.startswith("2025"):
            rows.append(
                {
                    "ts_code": ts_code,
                    "trade_date": "20260713",
                    "close": 100.0,
                }
            )
        return rows

    def trade_cal(
        self,
        *,
        exchange: str,
        is_open: str,
        start_date: str,
        end_date: str,
        fields: str,
    ) -> list[dict]:
        assert exchange == "SSE"
        assert is_open == "1"
        self.calendar_calls.append((start_date, end_date))
        return [
            {"cal_date": date.replace("-", ""), "is_open": "1"}
            for date in self.calendar_dates
            if start_date <= date.replace("-", "") <= end_date
        ]


def _snapshot(
    price_dates: list[str], *, calendar_dates: list[str] | None = None
) -> tuple[AssetSnapshot, dict, dict, bytes]:
    asset = _universe()["assets"][0]
    metadata = {"ts_code": asset["asset_id"], **asset["expected_index_basic"]}
    prices = [
        {"date": date, "close": 100.0 + index, "return_basis": "total_return"}
        for index, date in enumerate(price_dates)
    ]
    snapshot = AssetSnapshot(
        config=asset,
        metadata=metadata,
        prices=prices,
        query_start_date="20120101",
        query_end_date=AS_OF,
        query_chunk_count=15,
    )
    calendar_values = calendar_dates or price_dates
    calendar = {
        "as_of_date": calendar_values[-1],
        "dates": calendar_values,
    }
    serialized = (json.dumps(prices, sort_keys=True) + "\n").encode()
    import hashlib

    manifest_asset = {
        "price_file": "data/example.json",
        "price_file_sha256": hashlib.sha256(serialized).hexdigest(),
    }
    return snapshot, calendar, manifest_asset, serialized


def test_universe_is_exactly_five_ordered_strategy_style_assets() -> None:
    universe = _universe()
    assets = validate_universe_config(universe)
    assert [asset["asset_id"] for asset in assets] == [
        "CN2296.CNI",
        "CN2371.CNI",
        "H00015.CSI",
        "H00922.CSI",
        "480092.CNI",
    ]
    assert [asset["research_order"] for asset in assets] == [1, 2, 3, 4, 5]
    assert [asset["style_family"] for asset in assets] == [
        "growth",
        "value",
        "dividend",
        "dividend",
        "cash_flow",
    ]
    assert universe["excluded_scope"] == [
        "broad_base",
        "industry_theme",
        "resource_cycle",
        "other_assets",
    ]
    assert all(
        asset["official_code"] == asset["asset_id"].split(".", 1)[0]
        for asset in assets
    )


def test_growth_and_value_exact_metadata_pass() -> None:
    for asset in _universe()["assets"][:2]:
        row = {"ts_code": asset["asset_id"], **asset["expected_index_basic"]}
        assert validate_index_basic(asset, [row]) == row


def test_exact_metadata_difference_fails() -> None:
    asset = _universe()["assets"][0]
    row = {"ts_code": asset["asset_id"], **asset["expected_index_basic"]}
    row["fullname"] = "wrong"
    with pytest.raises(StrategyStyleDatasetError, match="metadata differs"):
        validate_index_basic(asset, [row])


@pytest.mark.parametrize("rows", [[], [{}, {}]])
def test_index_basic_requires_exactly_one_row(rows: list[dict]) -> None:
    asset = _universe()["assets"][0]
    with pytest.raises(StrategyStyleDatasetError, match="must return one row"):
        validate_index_basic(asset, rows)


def test_identity_only_still_checks_identity_and_required_fields() -> None:
    asset = _universe()["assets"][2]
    valid = {
        "ts_code": asset["asset_id"],
        "name": "provider name",
        "fullname": "provider full name",
        "market": "CSI",
        "category": "策略指数",
        "base_date": "20041231",
        "list_date": "20050104",
    }
    assert validate_index_basic(asset, [valid]) == valid
    invalid = dict(valid, ts_code="OTHER.CSI")
    with pytest.raises(StrategyStyleDatasetError, match="ts_code differs"):
        validate_index_basic(asset, [invalid])
    invalid = dict(valid, fullname="")
    with pytest.raises(StrategyStyleDatasetError, match="fullname is missing"):
        validate_index_basic(asset, [invalid])


def test_calendar_year_chunks_cover_long_history_without_truncation() -> None:
    chunks = year_chunks("2002", AS_OF)
    assert chunks[0] == ("20020101", "20021231")
    assert chunks[-1] == ("20260101", "20260715")
    assert len(chunks) == 25


def test_formal_builder_queries_index_daily_by_calendar_year() -> None:
    provider = FakeProvider()
    build_strategy_style_research_dataset(
        ROOT,
        as_of=AS_OF,
        provider=provider,
        generated_at="2026-07-16T00:00:00+00:00",
        publish=False,
    )
    value_calls = [call for call in provider.daily_calls if call[0] == "CN2371.CNI"]
    assert len(value_calls) == 25
    assert value_calls[0][1:] == ("20020101", "20021231")
    assert value_calls[-1][1:] == ("20260101", "20260715")


def test_cross_chunk_duplicate_price_date_fails() -> None:
    provider = FakeProvider()
    provider.duplicate_asset = "CN2296.CNI"
    with pytest.raises(StrategyStyleDatasetError, match="duplicate price date"):
        build_strategy_style_research_dataset(
            ROOT, as_of=AS_OF, provider=provider, publish=False
        )


def test_empty_price_history_fails() -> None:
    provider = FakeProvider()
    provider.empty_asset = "CN2296.CNI"
    with pytest.raises(StrategyStyleDatasetError, match="price history is empty"):
        build_strategy_style_research_dataset(
            ROOT, as_of=AS_OF, provider=provider, publish=False
        )


@pytest.mark.parametrize("bad_close", [math.nan, math.inf, -math.inf, 0.0, -1.0])
def test_invalid_close_values_fail(bad_close: float) -> None:
    raw = [
        {"ts_code": "A.CNI", "trade_date": "20260715", "close": bad_close}
    ]
    with pytest.raises(StrategyStyleDatasetError, match="invalid close"):
        validate_price_rows("A.CNI", raw, AS_OF)


def test_price_rows_are_sorted_and_total_return_only() -> None:
    raw = [
        {"ts_code": "A.CNI", "trade_date": "20260715", "close": 101},
        {"ts_code": "A.CNI", "trade_date": "20260714", "close": 100},
    ]
    assert validate_price_rows("A.CNI", raw, AS_OF) == [
        {"date": "2026-07-14", "close": 100.0, "return_basis": "total_return"},
        {"date": "2026-07-15", "close": 101.0, "return_basis": "total_return"},
    ]


@pytest.mark.parametrize(
    ("prices", "calendar"),
    [
        (["2026-07-13", "2026-07-15"], list(FAKE_DATES)),
        (list(FAKE_DATES) + ["2026-07-16"], list(FAKE_DATES)),
        (["2026-07-12", "2026-07-14", "2026-07-15"], list(FAKE_DATES)),
        (["2026-07-13", "2026-07-14"], list(FAKE_DATES)),
    ],
)
def test_calendar_mismatch_or_stale_history_blocks(
    prices: list[str], calendar: list[str]
) -> None:
    snapshot, calendar_row, manifest_asset, serialized = _snapshot(
        prices, calendar_dates=calendar
    )
    result = qualify_asset(snapshot, calendar_row, manifest_asset, serialized)
    assert result["qualified"] is False
    assert (
        result["checks"]["exact_sse_calendar_match"] is False
        or result["checks"]["ends_at_latest_open_session"] is False
    )


def test_matching_calendar_and_hash_qualifies() -> None:
    snapshot, calendar, manifest_asset, serialized = _snapshot(list(FAKE_DATES))
    result = qualify_asset(snapshot, calendar, manifest_asset, serialized)
    assert result["qualified"] is True
    assert result["blockers"] == []
    assert result["calendar_coverage"]["exact_calendar_match"] is True


def test_manifest_hash_mismatch_blocks() -> None:
    snapshot, calendar, manifest_asset, serialized = _snapshot(list(FAKE_DATES))
    manifest_asset["price_file_sha256"] = "0" * 64
    result = qualify_asset(snapshot, calendar, manifest_asset, serialized)
    assert result["qualified"] is False
    assert "price_file_sha256_matches_manifest" in result["blockers"]


def test_build_is_deterministic_except_generated_at_and_has_no_credentials() -> None:
    first = build_strategy_style_research_dataset(
        ROOT,
        as_of=AS_OF,
        provider=FakeProvider(),
        generated_at="2026-07-16T00:00:00+00:00",
        publish=False,
    )
    second = build_strategy_style_research_dataset(
        ROOT,
        as_of=AS_OF,
        provider=FakeProvider(),
        generated_at="2026-07-17T00:00:00+00:00",
        publish=False,
    )
    first.pop("generated_at")
    second.pop("generated_at")
    first.pop("source_manifest_sha256")
    second.pop("source_manifest_sha256")
    assert first == second
    serialized = json.dumps(first, ensure_ascii=False, allow_nan=False).lower()
    assert "test-token" not in serialized
    assert "tushare_token" not in serialized
    assert "authorization" not in serialized


def test_download_failure_leaves_existing_formal_snapshot_unchanged(
    tmp_path: Path,
) -> None:
    universe_target = tmp_path / UNIVERSE_RELATIVE
    universe_target.parent.mkdir(parents=True)
    universe_target.write_text(
        (ROOT / UNIVERSE_RELATIVE).read_text(encoding="utf-8"), encoding="utf-8"
    )
    data_target = tmp_path / DATASET_RELATIVE
    data_target.mkdir(parents=True)
    sentinel = data_target / "sentinel.json"
    sentinel.write_text('{"old": true}\n', encoding="utf-8")
    report_target = tmp_path / REPORT_RELATIVE
    report_target.parent.mkdir(parents=True)
    report_target.write_text('{"old": true}\n', encoding="utf-8")
    provider = FakeProvider()
    provider.fail_asset = "CN2371.CNI"

    with pytest.raises(RuntimeError, match="simulated download failure"):
        build_strategy_style_research_dataset(
            tmp_path, as_of=AS_OF, provider=provider, publish=True
        )

    assert sentinel.read_text(encoding="utf-8") == '{"old": true}\n'
    assert report_target.read_text(encoding="utf-8") == '{"old": true}\n'


def test_formal_generated_snapshot_inventory_and_fixed_counts_when_present() -> None:
    dataset = ROOT / DATASET_RELATIVE
    report_path = ROOT / REPORT_RELATIVE
    if not dataset.exists() or not report_path.exists():
        pytest.skip("formal network-generated snapshot has not been built yet")
    files = {
        path.relative_to(dataset).as_posix()
        for path in dataset.rglob("*")
        if path.is_file()
    }
    assert files == {
        "manifest.json",
        "sse_trade_calendar.json",
        "prices/CN2296_CNI.json",
        "prices/CN2371_CNI.json",
        "prices/H00015_CSI.json",
        "prices/H00922_CSI.json",
        "prices/480092_CNI.json",
    }
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = {row["asset_id"]: row for row in report["assets"]}
    assert rows["CN2296.CNI"]["row_count"] == 3284
    assert rows["CN2371.CNI"]["row_count"] == 5713
    assert report["overall_status"] == "QUALIFIED"
    assert report["summary"] == {
        "total_assets": 5,
        "qualified_assets": 5,
        "blocked_assets": 0,
        "growth_assets": 1,
        "value_assets": 1,
        "dividend_assets": 2,
        "cash_flow_assets": 1,
    }
