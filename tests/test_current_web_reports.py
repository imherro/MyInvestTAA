import json
from pathlib import Path

from fastapi.testclient import TestClient

import backend.current_web as current_web
from backend.main import app


CLIENT = TestClient(app)


def test_pages_show_current_report_fields_and_instrument_names() -> None:
    expected = {
        "/": ("2026-07-14", "南方中证500ETF", "510500.SH"),
        "/allocation": ("科创50全收益", "000688CNY01.CSI", "嘉实上证科创板芯片ETF"),
        "/research": ("12.05%", "-52.76%", "0.647"),
        "/shadow": ("同期市场背景", "南方中证500ETF", "2026-07-14"),
        "/data": ("国证自由现金流指数R", "480092.CNI", "华夏国证自由现金流ETF"),
        "/site-map": ("当前配置", "指数研究", "ETF Shadow"),
    }
    for path, values in expected.items():
        text = CLIENT.get(path).text
        for value in values:
            assert value in text


def test_navigation_and_site_map_only_link_to_current_pages() -> None:
    for path in current_web.PAGE_BUILDERS:
        text = CLIENT.get(path).text
        for target in current_web.PAGE_BUILDERS:
            assert f'href="{target}"' in text
        assert "/current-decision" not in text
        assert "/system-status" not in text


def test_failed_current_status_never_falls_back_to_old_reports(tmp_path: Path, monkeypatch) -> None:
    for name in current_web.REPORT_NAMES:
        payload = {"status": "failed", "current": False, "error": "provider failed"} if name == "data_status" else {}
        (tmp_path / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(current_web, "REPORT_DIR", tmp_path)

    for path in current_web.PAGE_BUILDERS:
        response = CLIENT.get(path)
        assert response.status_code == 503
        assert "CURRENT_TAA 当前不可用" in response.text
        assert "V11" not in response.text
        assert "Execution V1" not in response.text


def test_missing_current_report_never_falls_back_to_old_reports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(current_web, "REPORT_DIR", tmp_path)
    response = CLIENT.get("/")
    assert response.status_code == 503
    assert "缺少当前报告" in response.text
    assert "V11" not in response.text
