import json

from data_pipeline import build_full_validation_report
from storage import MarketDataRepository, connect_database


ASSET_IDS = ["510300", "512890", "511010", "518880"]


def _full_report(report_path=None, config=None) -> tuple[dict, MarketDataRepository]:
    repository = MarketDataRepository(connect_database(":memory:"))
    report = build_full_validation_report(
        repository,
        provider_name="mock",
        start_date="2020-01-01",
        end_date="2026-07-08",
        asset_ids=ASSET_IDS,
        report_path=report_path,
        config=config,
    )
    return report, repository


def test_full_validation_report_returns_required_sections():
    report, _ = _full_report(report_path=None)

    assert {"experiment", "dataset", "config", "performance", "benchmark", "attribution", "reproducibility"} <= set(report)


def test_full_validation_report_records_dataset_metadata():
    report, _ = _full_report(report_path=None)

    assert report["dataset"]["provider"] == "mock"
    assert report["dataset"]["asset_count"] == len(ASSET_IDS)
    assert report["dataset"]["rows"] > 0


def test_full_validation_report_records_performance_metrics():
    report, _ = _full_report(report_path=None)

    assert {"annual_return", "max_drawdown", "sharpe", "calmar", "ending_value"} <= set(report["performance"])


def test_full_validation_report_records_benchmark_rows():
    report, _ = _full_report(report_path=None)

    assert report["benchmark"]["HS300"]["strategy_id"] == "HS300_BUY_HOLD"
    assert report["benchmark"]["SAA_CLASSIC"]["strategy_id"] == "SAA_CLASSIC"


def test_full_validation_report_records_asset_attribution():
    report, _ = _full_report(report_path=None)

    assert "asset_contribution" in report["attribution"]
    assert "top_contributors" in report["attribution"]


def test_full_validation_report_records_regime_contribution():
    report, _ = _full_report(report_path=None)

    assert {"contribution", "periods", "dominant_regime"} <= set(report["attribution"]["regime_contribution"])


def test_full_validation_report_records_reproducibility_keys():
    report, _ = _full_report(report_path=None)

    assert report["reproducibility"]["dataset_id"] == report["dataset"]["dataset_id"]
    assert report["reproducibility"]["config_hash"] == report["experiment"]["config_hash"]


def test_full_validation_report_saves_dataset_version():
    report, repository = _full_report(report_path=None)

    assert repository.get_dataset_version(report["dataset"]["dataset_id"]) is not None


def test_full_validation_report_saves_experiment():
    report, repository = _full_report(report_path=None)

    assert repository.get_experiment(report["experiment"]["experiment_id"]) is not None


def test_full_validation_report_writes_json_file(tmp_path):
    path = tmp_path / "full_validation_report.json"

    report, _ = _full_report(report_path=path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["experiment"]["experiment_id"] == report["experiment"]["experiment_id"]


def test_full_validation_report_uses_config_costs():
    config = {
        "backtest": {
            "transaction_cost": 0.002,
            "slippage": 0.003,
            "expense_ratio": 0.004,
            "cash_return": 0.01,
            "rebalance_frequency": "monthly",
            "return_type": "price",
        },
        "risk": {},
        "universe": {"min_quality_score": 50.0},
    }

    report, _ = _full_report(report_path=None, config=config)

    assert report["config"]["backtest"]["transaction_cost"] == 0.002


def test_full_validation_report_can_use_total_return_label():
    repository = MarketDataRepository(connect_database(":memory:"))

    report = build_full_validation_report(
        repository,
        provider_name="mock",
        start_date="2020-01-01",
        end_date="2026-07-08",
        asset_ids=ASSET_IDS,
        return_type="total_return",
        report_path=None,
    )

    assert report["dataset"]["return_type"] == "total_return"


def test_full_validation_report_experiment_id_uses_config_hash_prefix():
    report, _ = _full_report(report_path=None)

    assert report["experiment"]["config_hash"][:8] in report["experiment"]["experiment_id"]


def test_full_validation_report_quality_score_is_present():
    report, _ = _full_report(report_path=None)

    assert report["dataset"]["quality_score"] >= 50
