import pytest

from config import (
    build_config_hash,
    load_backtest_config,
    load_config,
    load_research_config,
    load_risk_config,
    load_universe_config,
)
from config.loader import _parse_simple_yaml


def test_load_backtest_config_contains_cost_assumptions():
    config = load_backtest_config()

    assert {"transaction_cost", "slippage", "expense_ratio", "rebalance_frequency"} <= set(config)


def test_load_backtest_config_contains_return_type():
    assert load_backtest_config()["return_type"] == "price"


def test_load_risk_config_contains_max_asset_weight():
    assert load_risk_config()["max_asset_weight"] == 40.0


def test_load_universe_config_contains_benchmarks():
    config = load_universe_config()

    assert config["benchmark_equity"] == 510300
    assert config["benchmark_bond"] == 511010
    assert config["benchmark_gold"] == 518880


def test_load_research_config_groups_sections():
    config = load_research_config()

    assert {"backtest", "risk", "universe"} <= set(config)


def test_build_config_hash_is_stable_for_key_order():
    left = build_config_hash({"b": 2, "a": 1})
    right = build_config_hash({"a": 1, "b": 2})

    assert left == right


def test_build_config_hash_changes_when_value_changes():
    assert build_config_hash({"a": 1}) != build_config_hash({"a": 2})


def test_load_config_adds_yaml_suffix():
    assert load_config("backtest")["rebalance_frequency"] == "monthly"


def test_load_config_rejects_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("missing_config")


def test_parse_simple_yaml_reads_numbers_booleans_and_lists():
    parsed = _parse_simple_yaml("a: 1\nb: 1.5\nc: true\nd: [x, 2]\n")

    assert parsed == {"a": 1, "b": 1.5, "c": True, "d": ["x", 2]}


def test_parse_simple_yaml_rejects_invalid_line():
    with pytest.raises(ValueError):
        _parse_simple_yaml("invalid")


def test_universe_config_min_quality_score_is_numeric():
    assert isinstance(load_universe_config()["min_quality_score"], float)
