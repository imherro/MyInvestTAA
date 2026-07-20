import json
from pathlib import Path

from fastapi.testclient import TestClient

import backend.current_web as current_web
from backend.main import app


CLIENT = TestClient(app)
P2_SOURCE = Path("data/strategy_style_walk_forward_v1")


def test_strategy_center_keeps_formal_and_failed_strategies_visible() -> None:
    response = CLIENT.get("/strategies")

    assert response.status_code == 200
    for expected in (
        "策略中心", "CURRENT_TAA", "FORMAL / TRACKING", "风格回撤再平衡",
        "REJECTED / CLOSED", "查看失败原因与研究结果",
    ):
        assert expected in response.text


def test_current_taa_strategy_contains_full_user_workflow() -> None:
    response = CLIENT.get("/strategies/current-taa")

    assert response.status_code == 200
    for expected in (
        "策略状态：正式运行", "Execution V1", "自动交易", "否", "6 个月动量",
        "12.05%", "-52.76%", "0.647", "研究资产", "当前配置",
        "半导体材料设备全收益", "嘉实上证科创板芯片ETF", "映射质量",
        "调仓记录", "2026-06-30", "2026-07-14", "Shadow正式启用",
        "Shadow 跟踪", "不是券商实盘账户", "Execution V2 B1", "Execution V2 B2",
    ):
        assert expected in response.text


def test_p2_strategy_shows_research_failure_and_unreached_stages() -> None:
    response = CLIENT.get("/strategies/p2-style-drawdown")

    assert response.status_code == 200
    for expected in (
        "REJECTED / CLOSED", "研究过程", "1122", "PROFILE_A", "PROFILE_B", "PROFILE_C",
        "NOT_SUPPORTED", "为什么失败", "当前配置", "未生成", "调仓记录", "无",
        "Shadow 跟踪", "未启动", "CURRENT_TAA 集成", "DENIED", "DO_NOT_INTEGRATE",
    ):
        assert expected in response.text
    for year in range(2018, 2026):
        assert f">{year}<" in response.text


def test_p2_loader_only_requires_manifest_and_summary(tmp_path: Path) -> None:
    for name in current_web.P2_REPORT_NAMES:
        (tmp_path / f"{name}.json").write_bytes((P2_SOURCE / f"{name}.json").read_bytes())
    (tmp_path / "event_outcomes.json").mkdir()

    reports = current_web.load_p2_strategy(tmp_path)

    assert set(reports) == {"manifest", "walk_forward_summary"}


def test_strategy_center_isolates_missing_current_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(current_web, "REPORT_DIR", tmp_path)

    center = CLIENT.get("/strategies")
    current = CLIENT.get("/strategies/current-taa")

    assert center.status_code == 200
    assert "结果文件不可用" in center.text
    assert "不可核对" in center.text
    assert "REJECTED / CLOSED" in center.text
    assert current.status_code == 503
    assert "缺少当前报告" in current.text


def test_strategy_center_isolates_missing_p2_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(current_web, "P2_REPORT_DIR", tmp_path)

    center = CLIENT.get("/strategies")
    p2 = CLIENT.get("/strategies/p2-style-drawdown")

    assert center.status_code == 200
    assert "FORMAL / TRACKING" in center.text
    assert "结果文件不可用" in center.text
    assert "不可核对" in center.text
    assert p2.status_code == 503
    assert "缺少 P2 研究结果" in p2.text


def test_p2_page_rejects_manifest_summary_decision_mismatch(tmp_path: Path) -> None:
    for name in current_web.P2_REPORT_NAMES:
        payload = json.loads((P2_SOURCE / f"{name}.json").read_text(encoding="utf-8"))
        if name == "walk_forward_summary":
            payload["mechanism_decision"] = "SUPPORTED"
        (tmp_path / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")

    response = current_web.render_p2_strategy_page(tmp_path)

    assert response.status_code == 503
    assert "manifest 与 summary 结论不一致" in response.body.decode("utf-8")


def test_navigation_and_site_map_include_strategy_routes() -> None:
    for path in current_web.PUBLIC_PATHS:
        text = CLIENT.get(path).text
        assert 'href="/strategies"' in text
        assert text.count('class="active"') == 1
    site_map = CLIENT.get("/site-map").text
    assert 'href="/strategies/current-taa"' in site_map
    assert 'href="/strategies/p2-style-drawdown"' in site_map


def test_pages_make_no_trading_or_return_promises() -> None:
    for path in current_web.PUBLIC_PATHS:
        text = CLIENT.get(path).text
        assert "建议买入" not in text
        assert "自动交易：是" not in text
        assert "实盘收益保证" not in text
