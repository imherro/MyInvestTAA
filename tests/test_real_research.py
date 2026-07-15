from data_pipeline import build_dataset_version


def test_build_dataset_version_uses_end_date_in_id():
    version = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["510300"])

    assert version.dataset_id == "20260708_MOCK_CN_ETF"


def test_build_dataset_version_checksum_is_stable():
    one = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["510300"])
    two = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["510300"])

    assert one.checksum == two.checksum


def test_build_dataset_version_checksum_changes_with_assets():
    one = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["510300"])
    two = build_dataset_version("mock", "2016-01-01", "2026-07-08", ["512890"])

    assert one.checksum != two.checksum
