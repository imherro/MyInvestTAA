from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from release.web_contracts import primary_navigation_html


TEMPLATES = Jinja2Templates(directory=Path(__file__).with_name("templates"))
router = APIRouter()


SITE_MAP_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "title": "主要使用路径",
        "description": "普通用户按顺序阅读，先看结论，再看依据和系统状态。",
        "level": "primary",
        "routes": (
            ("/", "系统首页", "确认日期、发布状态和当前入口。"),
            ("/current-decision", "当前配置决策", "查看当前权重、策略净值和执行限制。"),
            ("/v11-current-allocation", "V11 模型配置", "核对正式候选模型的离线配置。"),
            ("/research-validation", "研究与执行验证", "进入研究与 ETF 执行证据频道。"),
            ("/system-status", "系统与数据状态", "核查发布、数据和完整性状态。"),
        ),
    },
    {
        "title": "研究与执行验证",
        "description": "用于解释研究指数、ETF 映射、历史验证和实验边界。",
        "level": "advanced",
        "routes": (
            ("/research-backtest", "研究资产历史验证", "研究指数层的历史配置结果。"),
            ("/execution-backtest", "ETF 执行验证", "研究配置映射到真实 ETF 后的差异。"),
            ("/shadow-portfolio", "Execution Shadow", "最新研究权重的实验性 ETF 映射。"),
            ("/research-universe", "研究与执行资产池", "核对指数、ETF、代码和映射关系。"),
            ("/benchmark-validation", "基准验证", "检查基准收益和回撤口径。"),
        ),
    },
)


def route_context(path: str) -> dict[str, str]:
    if path == "/site-map":
        return {"label": "网站地图", "level": "system", "parent": "/system-status"}
    for group in SITE_MAP_GROUPS:
        for route, label, _ in group["routes"]:
            if route == path:
                parent = (
                    "/research-validation"
                    if group["level"] in {"advanced", "audit"}
                    else "/site-map"
                )
                if group["level"] == "primary":
                    parent = "/" if route != "/" else ""
                return {"label": label, "level": group["level"], "parent": parent}
    return {"label": path, "level": "unclassified", "parent": "/site-map"}


@router.get("/site-map", name="site-map")
def site_map_page(request: Request):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="site_map.html",
        context={
            "primary_navigation": primary_navigation_html(),
            "groups": SITE_MAP_GROUPS,
        },
    )
