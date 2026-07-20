from __future__ import annotations

import copy
import json
from pathlib import Path

from current_taa.research_data_audit import (
    audit_research_universe,
    write_audit_report,
)
from current_taa.research_universe import load_research_universe
from data.models import PriceBar


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "research_universe_v1.json"


class FakeSource:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.requested: list[str] = []

    def get_research_history(self, asset_id: str, start: str, end: str) -> list[PriceBar]:
        self.requested.append(asset_id)
        if self.empty:
            return []
        return [
            PriceBar(asset_id=asset_id, date="2020-01-02", close=100.0),
            PriceBar(asset_id=asset_id, date="2020-01-03", close=101.0),
        ]


def test_offline_audit_marks_valid_confirmed_cache_ready(tmp_path: Path) -> None:
    _write_cache(
        tmp_path,
        "H00300.CSI",
        [
            {"date": "2020-01-02", "close": 100.0, "return_basis": "total_return"},
            {"date": "2020-01-03", "close": 101.0, "return_basis": "total_return"},
        ],
    )
    report = audit_research_universe(
        load_research_universe(CONTRACT),
        root=tmp_path,
        mode="offline",
        generated_at="2026-07-16T00:00:00+00:00",
    )
    row = _row(report, "csi300_total_return")

    assert row["local_cache_status"] == "available"
    assert row["provider_status"] == "not_checked"
    assert row["return_basis_status"] == "confirmed"
    assert row["contract_verification_status"] == "verified"
    assert row["contract_research_status"] == "available"
    assert row["research_ready"] is True
    assert row["first_date"] == "2020-01-02"
    assert report["summary"]["total_whitelist_assets"] == 32
    assert len(report["assets"]) == 7


def test_blocked_asset_with_valid_cache_is_not_research_ready(tmp_path: Path) -> None:
    universe = _universe_with_status(tmp_path, "blocked")
    _write_valid_csi300_cache(tmp_path)

    row = _row(
        audit_research_universe(universe, root=tmp_path, mode="offline"),
        "csi300_total_return",
    )

    assert row["contract_research_status"] == "blocked"
    assert row["research_ready"] is False
    assert "contract research_status is blocked" in row["blockers"]


def test_pending_asset_with_valid_cache_is_not_research_ready(tmp_path: Path) -> None:
    universe = _universe_with_status(tmp_path, "pending")
    _write_valid_csi300_cache(tmp_path)

    row = _row(
        audit_research_universe(universe, root=tmp_path, mode="offline"),
        "csi300_total_return",
    )

    assert row["contract_research_status"] == "pending"
    assert row["research_ready"] is False
    assert "contract research_status is pending" in row["blockers"]


def test_offline_audit_detects_missing_duplicate_invalid_and_wrong_basis(
    tmp_path: Path,
) -> None:
    _write_cache(
        tmp_path,
        "H00300.CSI",
        [
            {"date": "2020-01-03", "close": 100.0, "return_basis": "price"},
            {"date": "2020-01-02", "close": 0.0, "return_basis": "price"},
            {"date": "2020-01-02", "close": 99.0, "return_basis": "price"},
        ],
    )
    report = audit_research_universe(
        load_research_universe(CONTRACT), root=tmp_path, mode="offline"
    )
    bad = _row(report, "csi300_total_return")
    missing = _row(report, "csi500_total_return")

    assert bad["local_cache_status"] == "invalid"
    assert bad["duplicate_dates"] == ["2020-01-02"]
    assert bad["invalid_price_count"] == 1
    assert bad["sorted_unique_dates"] is False
    assert bad["return_basis_status"] == "unresolved"
    assert bad["research_ready"] is False
    assert missing["local_cache_status"] == "missing"


def test_provider_check_uses_only_tier_a_and_does_not_upgrade_reference_basis(
    tmp_path: Path,
) -> None:
    source = FakeSource()
    report = audit_research_universe(
        load_research_universe(CONTRACT),
        root=tmp_path,
        mode="provider_check",
        source=source,
    )
    chinext = _row(report, "chinext_total_return")
    value = _row(report, "cni1000_value_total_return")

    assert len(source.requested) == 6
    assert "399606.SZ" in source.requested
    assert chinext["provider_status"] == "available"
    assert chinext["return_basis_status"] == "reference_only"
    assert chinext["research_ready"] is False
    assert "local research cache is missing" not in chinext["blockers"]
    assert any("without writing cache" in warning for warning in chinext["warnings"])
    assert value["provider_code"] is None
    assert value["provider_status"] == "unavailable"
    assert value["research_ready"] is False


def test_empty_provider_history_is_blocked_without_substitution(tmp_path: Path) -> None:
    source = FakeSource(empty=True)
    report = audit_research_universe(
        load_research_universe(CONTRACT),
        root=tmp_path,
        mode="provider_check",
        source=source,
    )

    assert all(row["research_ready"] is False for row in report["assets"])
    assert all(
        row["provider_status"] == "unavailable" for row in report["assets"]
    )
    assert all("substitute" not in " ".join(row["blockers"]) for row in report["assets"])


def test_report_is_deterministic_except_timestamp_and_contains_no_token(
    tmp_path: Path,
) -> None:
    universe = load_research_universe(CONTRACT)
    first = audit_research_universe(
        universe, root=tmp_path, mode="offline", generated_at="first"
    )
    second = audit_research_universe(
        universe, root=tmp_path, mode="offline", generated_at="second"
    )
    comparable_first = copy.deepcopy(first)
    comparable_second = copy.deepcopy(second)
    comparable_first.pop("generated_at")
    comparable_second.pop("generated_at")

    assert comparable_first == comparable_second
    output = tmp_path / "audit.json"
    write_audit_report(output, first)
    text = output.read_text(encoding="utf-8")
    assert "token" not in text.lower()
    assert "NaN" not in text
    assert json.loads(text)["generated_at"] == "first"


def _write_cache(root: Path, provider_code: str, rows: list[dict]) -> None:
    target = root / "data" / "research_prices"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{provider_code.replace('.', '_')}.json").write_text(
        json.dumps(rows), encoding="utf-8"
    )


def _write_valid_csi300_cache(root: Path) -> None:
    _write_cache(
        root,
        "H00300.CSI",
        [
            {"date": "2020-01-02", "close": 100.0, "return_basis": "total_return"},
            {"date": "2020-01-03", "close": 101.0, "return_basis": "total_return"},
        ],
    )


def _universe_with_status(tmp_path: Path, status: str):
    raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
    raw["assets"][0]["research_status"] = status
    contract = tmp_path / f"universe_{status}.json"
    contract.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return load_research_universe(contract)


def _row(report: dict, asset_key: str) -> dict:
    return next(row for row in report["assets"] if row["asset_key"] == asset_key)
