from data.universe import available_universe, load_china_etf_universe, universe_asset_ids, universe_by_category


def test_china_etf_universe_has_at_least_twenty_assets():
    assert len(load_china_etf_universe()) >= 20


def test_china_etf_universe_contains_required_fields():
    item = load_china_etf_universe()[0]

    assert {"id", "name", "category", "asset_class", "start_date", "end_date"} <= set(item)


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


def test_universe_lifecycle_start_dates_are_populated():
    assert all(item["start_date"] for item in load_china_etf_universe())


def test_available_universe_excludes_assets_before_listing():
    ids = {item["id"] for item in available_universe("2012-01-01")}

    assert "510300" not in ids


def test_available_universe_includes_assets_after_listing():
    ids = {item["id"] for item in available_universe("2026-07-08")}

    assert "510300" in ids


def test_available_universe_excludes_assets_after_end_date(monkeypatch):
    import data.universe.loader as loader

    loader.load_china_etf_universe.cache_clear()
    monkeypatch.setattr(
        loader,
        "load_china_etf_universe",
        lambda: [
            {
                "id": "OLD",
                "name": "Old ETF",
                "category": "test",
                "asset_class": "equity",
                "start_date": "2020-01-01",
                "end_date": "2024-12-31",
            }
        ],
    )

    assert loader.available_universe("2025-01-01") == []
