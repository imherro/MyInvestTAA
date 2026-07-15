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
            ("/execution-backtest-v2", "Execution V2 B1", "动态可投资时间线实验。"),
            ("/shadow-portfolio", "Execution Shadow", "最新研究权重的实验性 ETF 映射。"),
            ("/research-universe", "研究与执行资产池", "核对指数、ETF、代码和映射关系。"),
            ("/benchmark-validation", "基准验证", "检查基准收益和回撤口径。"),
            ("/diagnosis", "策略诊断", "查看历史策略版本的诊断证据。"),
            ("/production-readiness", "候选策略证据", "核查正式候选模型的准入证据。"),
        ),
    },
    {
        "title": "策略研究审计",
        "description": "保留给需要追溯策略演进和研究判断的高级用户。",
        "level": "audit",
        "routes": (
            ("/strategy-governance", "策略治理", "版本状态和治理边界。"),
            ("/selection-research", "选择研究", "资产选择证据。"),
            ("/strategy-promotion", "策略晋级", "稳定性和晋级规则。"),
            ("/adaptive-strategy", "自适应策略", "历史自适应选择研究。"),
            ("/risk-exposure", "风险暴露", "组合风险与暴露审计。"),
            ("/final-strategy", "历史策略汇总", "历史候选策略对照。"),
            ("/attribution", "归因分析", "历史评分归因。"),
        ),
    },
    {
        "title": "历史归档",
        "description": "早期研发页面，仅用于追溯；不应作为当前系统入口。",
        "level": "archived",
        "routes": (
            ("/legacy-dashboard", "早期 Dashboard", "早期样例看板。"),
            ("/research", "早期研究报告", "旧研究展示。"),
            ("/pipeline", "早期数据管道", "旧管道展示。"),
            ("/real-research", "早期真实数据页", "旧真实数据工作流。"),
            ("/validation", "早期验证页", "旧验证入口。"),
            ("/experiment", "早期实验页", "旧实验报告。"),
            ("/quality", "早期数据质量页", "旧数据质量报告。"),
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
