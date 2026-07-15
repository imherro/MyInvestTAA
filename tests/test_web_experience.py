from __future__ import annotations

from html.parser import HTMLParser

from fastapi.testclient import TestClient

from backend.main import app
from backend.site_map import SITE_MAP_GROUPS
from backend.web_presentation import find_unlabeled_asset_codes


CLIENT = TestClient(app)
FRAMEWORK_ROUTES = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.h1_count = 0
        self.forms = 0
        self.internal_links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if tag == "h1":
            self.h1_count += 1
        elif tag == "form":
            self.forms += 1
        elif tag == "a" and str(values.get("href", "")).startswith("/"):
            self.internal_links.append(str(values["href"]).split("#", 1)[0])


def _page_routes() -> list[str]:
    return sorted(
        route.path
        for route in app.routes
        if getattr(route, "methods", None)
        and "GET" in route.methods
        and not route.path.startswith("/api/")
        and route.path not in FRAMEWORK_ROUTES
    )


def test_every_page_returns_200_and_has_readable_structure():
    for route in _page_routes():
        response = CLIENT.get(route)
        parser = _PageParser()
        parser.feed(response.text)
        assert response.status_code == 200, route
        assert parser.h1_count == 1, route
        assert parser.forms == 0, route
        assert 'name="viewport"' in response.text, route
        assert 'data-global-readability="true"' in response.text, route
        assert 'class="page-context"' in response.text, route


def test_every_visible_asset_code_has_a_registered_chinese_name():
    for route in _page_routes():
        response = CLIENT.get(route)
        assert find_unlabeled_asset_codes(response.text) == [], route


def test_requested_legacy_etf_and_research_index_are_labeled():
    html = CLIENT.get("/current-decision").text
    assert "512170 医疗ETF" in html
    assert "512170.SH 医疗ETF" in html
    assert "000688CNY01.CSI 科创50全收益" in html


def test_site_map_contains_every_non_framework_page_once():
    mapped = [
        route
        for group in SITE_MAP_GROUPS
        for route, _, _ in group["routes"]
    ]
    actual = [route for route in _page_routes() if route != "/site-map"]
    assert len(mapped) == len(set(mapped))
    assert sorted(mapped) == sorted(actual)


def test_all_internal_page_links_resolve_to_registered_routes():
    registered = {
        route.path
        for route in app.routes
        if getattr(route, "methods", None) and "GET" in route.methods
    }
    for route in _page_routes():
        parser = _PageParser()
        parser.feed(CLIENT.get(route).text)
        missing = sorted(
            link
            for link in set(parser.internal_links)
            if "{" not in link and link not in registered
        )
        assert missing == [], (route, missing)


def test_home_and_status_expose_site_map_without_expanding_primary_navigation():
    for route in ("/", "/system-status"):
        html = CLIENT.get(route).text
        assert 'href="/site-map"' in html
        nav = html.split('class="primary-nav"', 1)[1].split("</nav>", 1)[0]
        assert nav.count("<a ") == 5


def test_site_map_separates_current_research_audit_and_archived_pages():
    html = CLIENT.get("/site-map").text
    for heading in ("主要使用路径", "研究与执行验证", "策略研究审计", "历史归档"):
        assert heading in html
    assert 'section data-level="archived"' in html
    assert "历史归档不代表当前系统结论" in html
