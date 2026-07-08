from __future__ import annotations

from engine.stock_breadth.models import StockThemeMapping


DEFAULT_THEME_STOCK_MAPPING: dict[str, list[str]] = {
    "large_cap": ["600519.SH", "601318.SH", "600036.SH", "601166.SH", "600900.SH"],
    "mid_cap": ["600276.SH", "600309.SH", "000725.SZ", "002475.SZ", "300059.SZ"],
    "small_cap": ["300122.SZ", "300014.SZ", "300124.SZ", "002230.SZ", "002241.SZ"],
    "growth": ["300750.SZ", "300760.SZ", "300059.SZ", "300015.SZ", "300274.SZ"],
    "innovation": ["688981.SH", "688012.SH", "688008.SH", "688111.SH", "688599.SH"],
    "dividend": ["601398.SH", "601288.SH", "601988.SH", "600900.SH", "601088.SH"],
    "semiconductor": ["688981.SH", "603501.SH", "300782.SZ", "002371.SZ", "688012.SH"],
    "new_energy": ["300750.SZ", "002594.SZ", "601012.SH", "300274.SZ", "002129.SZ"],
    "healthcare": ["600276.SH", "300760.SZ", "000661.SZ", "600196.SH", "300015.SZ"],
    "consumer": ["600519.SH", "000858.SZ", "000568.SZ", "600887.SH", "000651.SZ"],
    "financial": ["600036.SH", "601398.SH", "601288.SH", "601166.SH", "000001.SZ"],
    "brokerage": ["600030.SH", "600837.SH", "601688.SH", "000776.SZ", "601211.SH"],
    "defense": ["600760.SH", "600893.SH", "000768.SZ", "002179.SZ", "600316.SH"],
    "cyclical": ["601899.SH", "603993.SH", "600111.SH", "000807.SZ", "601600.SH"],
    "gold": ["600547.SH", "000975.SZ", "600489.SH", "601899.SH", "000506.SZ"],
    "government_bond": [],
}


def stocks_for_theme(theme: str) -> list[str]:
    return list(DEFAULT_THEME_STOCK_MAPPING.get(theme, []))


def theme_for_stock(stock_id: str) -> str:
    for theme, stocks in DEFAULT_THEME_STOCK_MAPPING.items():
        if stock_id in stocks or stock_id.split(".", 1)[0] in {item.split(".", 1)[0] for item in stocks}:
            return theme
    return "unclassified"


def stock_theme_universe() -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for stocks in DEFAULT_THEME_STOCK_MAPPING.values():
        for stock in stocks:
            if stock not in seen:
                seen.add(stock)
                values.append(stock)
    return values


def load_stock_theme_mapping(themes: list[str] | None = None) -> list[dict]:
    selected = themes or sorted(DEFAULT_THEME_STOCK_MAPPING)
    rows: list[dict] = []
    for theme in selected:
        rows.extend(
            StockThemeMapping(stock=stock, theme=theme).as_dict()
            for stock in stocks_for_theme(theme)
        )
    return rows
