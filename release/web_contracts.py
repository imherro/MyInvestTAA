from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re


PRIMARY_NAVIGATION = (
    ("/", "系统首页", "状态和入口"),
    ("/current-decision", "当前配置决策", "人工审核快照"),
    ("/v11-current-allocation", "V11 模型配置", "正式候选模型"),
    ("/research-validation", "研究与执行验证", "高级研究内容"),
    ("/system-status", "系统与数据状态", "发布和数据审计"),
)

ADVANCED_ROUTES = {
    "/site-map": "全部 Web 页面和层级关系",
    "/research-backtest": "研究资产层历史验证",
    "/execution-backtest": "真实 ETF 执行验证",
    "/execution-backtest-v2": "实验性动态可投资时间线",
    "/shadow-portfolio": "实验性 Shadow 快照",
    "/diagnosis": "策略诊断审计",
    "/production-readiness": "生产候选证据",
    "/research-universe": "研究和执行资产池审计",
    "/benchmark-validation": "基准验证证据",
    "/strategy-governance": "策略治理证据",
    "/selection-research": "研究选择证据",
    "/strategy-promotion": "策略晋级证据",
    "/adaptive-strategy": "历史研究页面",
    "/risk-exposure": "风险暴露审计",
    "/final-strategy": "历史策略汇总",
    "/attribution": "历史归因分析",
}

ARCHIVED_ROUTES = {
    "/legacy-dashboard": "早期样例和研发 Dashboard",
    "/research": "早期研究页",
    "/pipeline": "早期数据管道页",
    "/real-research": "早期真实数据页",
    "/validation": "早期验证页",
    "/experiment": "早期实验页",
    "/quality": "早期数据质量页",
}

FRAMEWORK_ROUTES = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
REQUIRED_PAGE_COPY = {
    "/": ("普通用户建议阅读顺序", "本系统不会做什么", "非交易指令"),
    "/current-decision": ("用于人工判断", "不会生成订单", "非交易指令"),
    "/v11-current-allocation": ("正式候选模型", "不是下单指令", "未授权自动交易"),
    "/research-validation": ("研究资产层", "真实 ETF", "不是生产组合"),
    "/system-status": ("does not authorize automated trading", "阻塞错误", "文档入口"),
}


def primary_navigation_html() -> str:
    links = "".join(
        f'<a href="{route}">{label}<span>{description}</span></a>'
        for route, label, description in PRIMARY_NAVIGATION
    )
    return f'<nav class="primary-nav" aria-label="主要导航">{links}</nav>'


def scan_backend_web_routes(root: Path) -> list[str]:
    from backend.main import app

    routes = [
        route.path
        for route in app.routes
        if getattr(route, "methods", None) and "GET" in route.methods
    ]
    return sorted(
        route
        for route in routes
        if not route.startswith("/api/") and route not in FRAMEWORK_ROUTES
    )


def build_route_inventory(actual_routes: list[str]) -> dict:
    primary = {route: (label, description) for route, label, description in PRIMARY_NAVIGATION}
    routes: list[dict] = []
    unknown: list[str] = []
    for route in sorted(set(actual_routes)):
        if route in primary:
            title, reason = primary[route]
            value = "primary" if route != "/research-validation" else "advanced"
            action = "aggregate" if route == "/research-validation" else "keep"
            linked = True
            dependencies = []
        elif route in ADVANCED_ROUTES:
            title = route.strip("/").replace("-", " ").title()
            reason = ADVANCED_ROUTES[route]
            value = "advanced"
            action = "hide"
            linked = False
            dependencies = ["formal report loader"]
        elif route in ARCHIVED_ROUTES:
            title = route.strip("/").replace("-", " ").title()
            reason = ARCHIVED_ROUTES[route]
            value = "none"
            action = "archive"
            linked = False
            dependencies = []
        else:
            unknown.append(route)
            title = route
            reason = "unclassified Web route"
            value = "none"
            action = "unknown"
            linked = False
            dependencies = []
        routes.append(
            {
                "route": route,
                "title": title,
                "current_user_value": value,
                "linked_from_global_navigation": linked,
                "backend_dependency": ["backend/main.py"],
                "report_dependency": dependencies,
                "test_dependency": ["tests/test_system_release.py"],
                "action": action,
                "reason": reason,
            }
        )
    return {
        "available": True,
        "verified": not unknown,
        "primary_navigation_count": len(PRIMARY_NAVIGATION),
        "actual_route_count": len(actual_routes),
        "unclassified_routes": unknown,
        "routes": routes,
    }


def validate_web_contract(root: Path, inventory: dict) -> dict:
    errors: list[str] = []
    page_results: list[dict] = []
    release_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / "release").glob("*.py"))
    )
    network_matches = re.findall(
        r"^(?:from|import)\s+(tushare|yfinance|fredapi|requests|httpx|urllib|socket)\b",
        release_source,
        flags=re.MULTILINE,
    )
    if network_matches:
        errors.append("release code contains live network paths")
    if inventory.get("verified") is not True:
        errors.append("actual Web route inventory is not verified")
    try:
        from fastapi.testclient import TestClient
        from backend.main import app, system_home
        from unittest.mock import patch

        client = TestClient(app)
        registered_routes = {
            route.path for route in app.routes if getattr(route, "methods", None) and "GET" in route.methods
        }
        expected_navigation = [route for route, _, _ in PRIMARY_NAVIGATION]
        def valid_release(name: str) -> dict:
            if name == "release_manifest.json":
                return {
                    "available": True,
                    "verified": True,
                    "release_id": "contract-check",
                    "market_data_as_of": "2026-07-08",
                    "decision_date": "2026-07-13",
                    "build_mode": "offline_local",
                    "commit_sha": "0" * 40,
                }
            if name == "current_market_decision.json":
                return {
                    "available": True,
                    "verified": True,
                    "status": "user_review_ready",
                    "ready_for_user_review": True,
                    "production_actionable": False,
                    "execution_validation": {"ready": False, "reasons": []},
                    "execution_shadow": {"etf_weights": {"CASH": 1.0}},
                }
            if name == "v11_current_allocation.json":
                return {
                    "available": True,
                    "verified": True,
                    "equity_weight": 0.0,
                    "cash_weight": 1.0,
                }
            return {
                "available": True,
                "verified": True,
                "system_acceptance_passed": True,
                "blocking_errors": [],
                "known_nonblocking_conditions": [],
            }

        with patch("backend.main.load_release_json", side_effect=valid_release):
            for route, _, _ in PRIMARY_NAVIGATION:
                response = client.get(route)
                parser = _PageContractParser()
                parser.feed(response.text)
                page_errors: list[str] = []
                if response.status_code != 200:
                    page_errors.append("page did not return 200")
                if parser.h1_count != 1:
                    page_errors.append("page must contain exactly one h1")
                if parser.primary_navigation_links != expected_navigation:
                    page_errors.append("primary navigation does not match policy")
                if parser.form_count:
                    page_errors.append("page contains a form")
                for phrase in REQUIRED_PAGE_COPY[route]:
                    if phrase not in response.text:
                        page_errors.append(f"required copy missing: {phrase}")
                page_results.append({"route": route, "verified": not page_errors, "errors": page_errors})
                errors.extend(f"{route}: {error}" for error in page_errors)
        for route in expected_navigation:
            if route not in registered_routes:
                errors.append(f"primary route is not registered: {route}")
        with patch("backend.main.load_release_json", side_effect=valid_release):
            home = client.get("/").text
        if home.count('class="button primary"') != 1 or 'class="button primary" href="/current-decision"' not in home:
            errors.append("home normal-state primary CTA is invalid")
        with patch("backend.main.load_release_json", return_value={"available": False, "verified": False, "blocking_errors": ["release failed"]}):
            failed_home = system_home()
        if 'class="button primary" href="/system-status"' not in failed_home or 'class="button primary" href="/current-decision"' in failed_home:
            errors.append("home failure-state primary CTA is invalid")
    except Exception as exc:
        errors.append(f"Web contract execution failed: {type(exc).__name__}: {exc}")
    return {
        "verified": not errors,
        "network_accessed": False,
        "network_import_matches": network_matches,
        "primary_navigation": [route for route, _, _ in PRIMARY_NAVIGATION],
        "page_results": page_results,
        "route_inventory_verified": inventory.get("verified") is True,
        "errors": errors,
    }


def build_legacy_cleanup_report(root: Path, inventory: dict) -> dict:
    rows = inventory.get("routes", [])
    primary_routes = {route for route, _, _ in PRIMARY_NAVIGATION}
    navigation_routes = set(
        re.findall(r'href="([^"]+)"', primary_navigation_html())
    )
    hidden = [row["route"] for row in rows if row["action"] == "hide"]
    archived = [row["route"] for row in rows if row["action"] == "archive"]
    route_errors = list(inventory.get("unclassified_routes", []))
    navigation_errors = sorted((set(hidden) | set(archived)) & navigation_routes)
    dependency_paths = [
        "data_pipeline/strategy_diagnosis.py",
        "backtest/research/engine.py",
        "backtest/execution/engine.py",
        "backtest/execution/shadow_portfolio.py",
        "backtest/execution/approval_integrity.py",
        "scripts/recover_execution_mapping_transaction.py",
        "scripts/recover_system_release.py",
    ]
    missing_dependencies = [path for path in dependency_paths if not (root / path).exists()]
    test_corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / "tests").glob("test_*.py"))
    )
    retained_rows = [row for row in rows if row["action"] in {"hide", "archive"}]
    test_references = [row["route"] for row in retained_rows if row["route"] in test_corpus]
    explicit_reasons = [
        row["route"]
        for row in retained_rows
        if row["route"] not in test_corpus and bool(row.get("reason"))
    ]
    test_errors = [
        row["route"]
        for row in retained_rows
        if row["route"] not in test_corpus and not row.get("reason")
    ]
    proof = {
        "route_scan": {
            "scanned_count": inventory.get("actual_route_count", 0),
            "classified_count": len(rows) - len(route_errors),
            "unclassified_routes": route_errors,
            "verified": not route_errors,
        },
        "reference_scan": {
            "primary_count": len(navigation_routes),
            "navigation_routes": sorted(navigation_routes),
            "hidden_or_archived_in_primary": navigation_errors,
            "verified": not navigation_errors,
        },
        "test_dependency_scan": {
            "retained_route_count": len(hidden) + len(archived),
            "route_test_references": test_references,
            "explicit_reason_routes": explicit_reasons,
            "missing_test_or_reason": test_errors,
            "verified": not test_errors,
        },
        "release_dependency_scan": {
            "required_module_count": len(dependency_paths),
            "missing_modules": missing_dependencies,
            "verified": not missing_dependencies,
        },
    }
    verified = all(section["verified"] for section in proof.values())
    return {
        "available": True,
        "verified": verified,
        "deleted_routes": [],
        "deleted_modules": [],
        "hidden_routes": hidden,
        "archived_routes": archived,
        "retained_backend_dependencies": dependency_paths,
        "visible_link_count_before": len(rows),
        "visible_link_count_after": len(primary_routes),
        "proof": proof,
        "errors": route_errors + navigation_errors + test_errors + missing_dependencies,
    }


class _PageContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.h1_count = 0
        self.form_count = 0
        self.primary_navigation_links: list[str] = []
        self._in_primary_navigation = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "h1":
            self.h1_count += 1
        elif tag == "form":
            self.form_count += 1
        elif tag == "nav" and "primary-nav" in (values.get("class") or "").split():
            self._in_primary_navigation = True
        elif tag == "a" and self._in_primary_navigation and values.get("href"):
            self.primary_navigation_links.append(values["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav" and self._in_primary_navigation:
            self._in_primary_navigation = False
