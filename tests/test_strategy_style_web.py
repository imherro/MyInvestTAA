import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.current_web as current_web
from backend.main import app
from backend.strategy_style_research_view import load_strategy_style_research_view


CLIENT = TestClient(app)


def test_formal_rejected_result_is_clear_and_kept_out_of_current_taa() -> None:
    home = CLIENT.get("/")
    research = CLIENT.get("/research")

    assert home.status_code == 200
    assert "策略风格回撤再平衡：未获支持" in home.text
    assert "该结论不改变 CURRENT_TAA 当前配置" in home.text
    assert research.status_code == 200
    assert "数据截至 2026-07-15" in research.text
    assert "0 / 3" in research.text
    assert "不进入" in research.text
    assert "PROFILE_" not in research.text
    for profile in ("方案 A", "方案 B", "方案 C"):
        assert profile in research.text
    for h60_median in ("-1.98%", "-3.53%", "-4.22%"):
        assert h60_median in research.text


def test_research_result_loader_rejects_changed_downstream_status(tmp_path: Path) -> None:
    source_dir = Path("data/strategy_style_walk_forward_v1")
    for name in ("manifest.json", "walk_forward_summary.json"):
        payload = json.loads((source_dir / name).read_text(encoding="utf-8"))
        if name == "manifest.json":
            payload["statuses"]["integration_status"] = "INTEGRATE"
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="下游禁用状态不一致"):
        load_strategy_style_research_view(tmp_path)


def test_missing_p2_result_does_not_break_current_pages(monkeypatch) -> None:
    def unavailable():
        raise ValueError("missing")

    monkeypatch.setattr(current_web, "load_strategy_style_research_view", unavailable)
    response = CLIENT.get("/research")

    assert response.status_code == 200
    assert "全收益指数长期研究" in response.text
    assert "策略风格研究结果暂不可用" in response.text


def test_navigation_marks_only_the_current_page() -> None:
    for path in current_web.PAGE_BUILDERS:
        text = CLIENT.get(path).text
        assert text.count('class="active"') == 1
