import json
from pathlib import Path

import pytest

from data.models import PriceBar
from scripts.update_market_data import (
    BACKGROUND_BENCHMARK_ID,
    _load_enabled_configuration,
    update_market_data,
)


class FakeSource:
    def __init__(self, fail_asset: str | None = None) -> None:
        self.fail_asset = fail_asset

    def get_research_history(self, asset_id: str, start: str, end: str) -> list[PriceBar]:
        return self._history(asset_id, start, end)

    def get_execution_history(self, asset_id: str, start: str, end: str) -> list[PriceBar]:
        return self._history(asset_id, start, end)

    def get_trade_dates(self, start: str, end: str) -> list[str]:
        return [start.replace("-", ""), end.replace("-", "")]

    def _history(self, asset_id: str, start: str, end: str) -> list[PriceBar]:
        if asset_id == self.fail_asset:
            raise RuntimeError(f"failed {asset_id}")
        return [PriceBar(asset_id, start, 1.0), PriceBar(asset_id, end, 1.1)]


def _prepare_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "data" / "research_prices").mkdir(parents=True)
    (root / "data" / "execution_prices").mkdir()
    (root / "data" / "market").mkdir()
    (root / "reports" / "current").mkdir(parents=True)
    assets = [
        {
            "asset_id": "INDEX.A",
            "name": "指数A",
            "category": "broad_base",
            "data_source": "tushare",
            "enabled": True,
        },
        {
            "asset_id": "INDEX.B",
            "name": "指数B",
            "category": "theme",
            "data_source": "tushare",
            "enabled": True,
        },
    ]
    mappings = [
        {
            "research_asset_id": "INDEX.A",
            "etf_id": BACKGROUND_BENCHMARK_ID,
            "etf_name": "中证500ETF",
            "enabled": True,
        },
        {
            "research_asset_id": "INDEX.B",
            "etf_id": BACKGROUND_BENCHMARK_ID,
            "etf_name": "中证500ETF",
            "enabled": True,
        },
    ]
    (root / "config" / "research_assets.json").write_text(
        json.dumps(assets, ensure_ascii=False), encoding="utf-8"
    )
    (root / "config" / "etf_mappings.json").write_text(
        json.dumps(mappings, ensure_ascii=False), encoding="utf-8"
    )
    (root / "data" / "research_prices" / "old.json").write_text("old", encoding="utf-8")
    (root / "data" / "execution_prices" / "old.json").write_text("old", encoding="utf-8")
    (root / "data" / "market" / "old.json").write_text("old", encoding="utf-8")
    (root / "reports" / "current" / "manifest.json").write_text("old", encoding="utf-8")
    return root


def test_configuration_counts_mappings_but_deduplicates_etfs(tmp_path):
    root = _prepare_root(tmp_path)

    assets, mappings, execution_ids = _load_enabled_configuration(root)

    assert len(assets) == 2
    assert len(mappings) == 2
    assert execution_ids == [BACKGROUND_BENCHMARK_ID]


def test_success_replaces_all_raw_data_before_running_current(tmp_path):
    root = _prepare_root(tmp_path)
    observed = []

    def current_runner() -> None:
        observed.append((root / "data" / "execution_prices" / "510500_SH.json").exists())
        (root / "reports" / "current" / "manifest.json").write_text("new", encoding="utf-8")

    manifest = update_market_data(
        root=root,
        start="2026-01-02",
        end="2026-01-05",
        source=FakeSource(),
        current_runner=current_runner,
    )

    assert observed == [True]
    assert manifest["mapping_count"] == 2
    assert manifest["unique_asset_count"] == 1
    assert {path.name for path in (root / "data" / "research_prices").iterdir()} == {
        "INDEX_A.json",
        "INDEX_B.json",
    }
    assert {path.name for path in (root / "data" / "execution_prices").iterdir()} == {
        "510500_SH.json",
        "manifest.json",
    }
    rows = json.loads(
        (root / "data" / "research_prices" / "INDEX_A.json").read_text(encoding="utf-8")
    )
    assert {row["return_basis"] for row in rows} == {"total_return"}
    assert (root / "reports" / "current" / "manifest.json").read_text(encoding="utf-8") == "new"


def test_fetch_failure_keeps_previous_data_and_does_not_run_current(tmp_path):
    root = _prepare_root(tmp_path)
    calls = []

    with pytest.raises(RuntimeError, match="failed INDEX.B"):
        update_market_data(
            root=root,
            start="2026-01-02",
            end="2026-01-05",
            source=FakeSource(fail_asset="INDEX.B"),
            current_runner=lambda: calls.append(True),
        )

    assert calls == []
    assert (root / "data" / "research_prices" / "old.json").read_text(encoding="utf-8") == "old"
    assert (root / "reports" / "current" / "manifest.json").read_text(encoding="utf-8") == "old"


def test_current_failure_restores_previous_data_and_reports(tmp_path):
    root = _prepare_root(tmp_path)

    def fail_current() -> None:
        current = root / "reports" / "current"
        (current / "manifest.json").write_text("partial", encoding="utf-8")
        raise RuntimeError("current failed")

    with pytest.raises(RuntimeError, match="current failed"):
        update_market_data(
            root=root,
            start="2026-01-02",
            end="2026-01-05",
            source=FakeSource(),
            current_runner=fail_current,
        )

    for directory in ("research_prices", "execution_prices", "market"):
        assert (root / "data" / directory / "old.json").read_text(encoding="utf-8") == "old"
    assert (root / "reports" / "current" / "manifest.json").read_text(encoding="utf-8") == "old"


def test_update_script_has_no_legacy_data_stack_imports():
    source = (Path(__file__).parents[1] / "scripts" / "update_market_data.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("backtest", "data_pipeline", "storage", "engine.asset_registry"):
        assert forbidden not in source
