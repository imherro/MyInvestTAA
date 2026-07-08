from data.universe import load_china_etf_universe, universe_asset_ids, universe_by_category


def test_china_etf_universe_has_at_least_twenty_assets():
    assert len(load_china_etf_universe()) >= 20


def test_china_etf_universe_contains_required_fields():
    item = load_china_etf_universe()[0]

    assert {"id", "name", "category", "asset_class"} <= set(item)


def test_universe_asset_ids_include_core_etf():
    assert "510300" in universe_asset_ids()


def test_universe_categories_include_broad_base():
    grouped = universe_by_category()

    assert "broad_base" in grouped


def test_universe_categories_include_defensive_assets():
    grouped = universe_by_category()

    assert "defensive" in grouped


def test_universe_has_gold_and_bond():
    ids = set(universe_asset_ids())

    assert {"518880", "511010"} <= ids


def test_universe_asset_ids_are_unique():
    ids = universe_asset_ids()

    assert len(ids) == len(set(ids))
