from __future__ import annotations

import json
from dataclasses import dataclass
from math import sqrt
from pathlib import Path


MODEL_NAME = "CURRENT_TAA"
MODEL_DESCRIPTION = "趋势/回撤型多资产 TAA"
IMPLEMENTATION_VERSION = "1.0.0"


@dataclass(frozen=True)
class ModelConfig:
    lookback_6m: int = 126
    lookback_12m: int = 252
    top_n: int = 5
    min_assets: int = 5
    momentum_6m_weight: float = 0.4
    momentum_12m_weight: float = 0.3
    drawdown_resilience_weight: float = 0.3
    single_asset_max: float = 0.25
    single_theme_max: float = 0.10
    theme_total_max: float = 0.20


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_trade_dates(path: Path) -> list[str]:
    value = load_json(path)
    dates = []
    for raw in value.get("dates", []):
        text = str(raw)
        dates.append(f"{text[:4]}-{text[4:6]}-{text[6:]}" if len(text) == 8 else text)
    if not dates or dates != sorted(set(dates)):
        raise ValueError("trade calendar must contain sorted unique dates")
    return dates


def load_price_series(path: Path, expected_basis: str) -> list[dict]:
    rows = load_json(path)
    dates = []
    result = []
    for row in rows:
        date = str(row["date"])
        close = float(row["close"])
        basis = str(row.get("return_basis", ""))
        if close <= 0 or basis != expected_basis:
            raise ValueError(f"invalid {expected_basis} price row in {path.name}")
        dates.append(date)
        result.append({"date": date, "close": close})
    if not result or dates != sorted(set(dates)):
        raise ValueError(f"price rows must be sorted and unique in {path.name}")
    return result


def asset_file_name(asset_id: str) -> str:
    return asset_id.replace(".", "_") + ".json"


def compute_score(rows: list[dict], signal_date: str, cfg: ModelConfig | None = None) -> dict | None:
    config = cfg or ModelConfig()
    history = [row for row in rows if row["date"] <= signal_date]
    if len(history) <= config.lookback_12m or history[-1]["date"] != signal_date:
        return None
    current = history[-1]["close"]
    price_6m = history[-1 - config.lookback_6m]["close"]
    price_12m = history[-1 - config.lookback_12m]["close"]
    window = [row["close"] for row in history[-1 - config.lookback_12m :]]
    momentum_6m = current / price_6m - 1.0
    momentum_12m = current / price_12m - 1.0
    resilience = 1.0 + _max_drawdown_values(window)
    score = (
        config.momentum_6m_weight * momentum_6m
        + config.momentum_12m_weight * momentum_12m
        + config.drawdown_resilience_weight * resilience
    )
    return {
        "score": round(score, 8),
        "momentum_6m": round(momentum_6m, 8),
        "momentum_12m": round(momentum_12m, 8),
        "drawdown_resilience": round(resilience, 8),
    }


def build_target_weights(selected_assets: list[dict], cfg: ModelConfig | None = None) -> dict[str, float]:
    config = cfg or ModelConfig()
    if not selected_assets:
        return {"CASH": 1.0}
    base = 1.0 / len(selected_assets)
    weights: dict[str, float] = {}
    theme_used = 0.0
    for asset in selected_assets:
        cap = config.single_asset_max
        if asset["category"] == "theme":
            cap = min(cap, config.single_theme_max, max(config.theme_total_max - theme_used, 0.0))
        weight = min(base, cap)
        if weight > 0:
            weights[asset["asset_id"]] = weight
        if asset["category"] == "theme":
            theme_used += weight
    leftover = 1.0 - sum(weights.values())
    non_theme = [a for a in selected_assets if a["category"] != "theme"]
    while leftover > 1e-10:
        available = [a for a in non_theme if weights.get(a["asset_id"], 0.0) < config.single_asset_max - 1e-10]
        if not available:
            break
        addition = leftover / len(available)
        spent = 0.0
        for asset in available:
            asset_id = asset["asset_id"]
            add = min(addition, config.single_asset_max - weights.get(asset_id, 0.0))
            weights[asset_id] = weights.get(asset_id, 0.0) + add
            spent += add
        leftover -= spent
    if leftover > 1e-10:
        weights["CASH"] = leftover
    return {key: round(value, 10) for key, value in weights.items() if value > 1e-10}


def run_research(assets: list[dict], prices: dict[str, list[dict]], trade_dates: list[str]) -> dict:
    cfg = ModelConfig()
    enabled = [asset for asset in assets if asset.get("enabled") is True]
    if len(enabled) < cfg.min_assets:
        raise ValueError("CURRENT_TAA requires at least five enabled research assets")
    asset_by_id = {asset["asset_id"]: asset for asset in enabled}
    price_maps = {asset_id: {row["date"]: row["close"] for row in rows} for asset_id, rows in prices.items()}
    allocations = []
    current_weights = {"CASH": 1.0}
    equity_curve: list[dict] = []
    active = False

    for index in range(1, len(trade_dates)):
        date = trade_dates[index]
        previous_date = trade_dates[index - 1]
        is_first_day_of_month = date[:7] != previous_date[:7]
        if is_first_day_of_month:
            scored = []
            for asset in enabled:
                score = compute_score(prices[asset["asset_id"]], previous_date, cfg)
                if score is not None:
                    scored.append({"asset_id": asset["asset_id"], **score})
            if len(scored) >= cfg.min_assets:
                selected_rows = sorted(scored, key=lambda row: row["score"], reverse=True)[: cfg.top_n]
                selected_assets = [asset_by_id[row["asset_id"]] for row in selected_rows]
                current_weights = build_target_weights(selected_assets, cfg)
                allocations.append(
                    {
                        "signal_date": previous_date,
                        "effective_date": date,
                        "eligible_asset_count": len(scored),
                        "weights": current_weights,
                        "scores": {row["asset_id"]: {k: v for k, v in row.items() if k != "asset_id"} for row in selected_rows},
                    }
                )
                if not active:
                    equity_curve = [{"date": previous_date, "value": 1.0}]
                    active = True
        if not active:
            continue
        daily_return = 0.0
        for asset_id, weight in current_weights.items():
            if asset_id == "CASH":
                continue
            previous = price_maps[asset_id].get(previous_date)
            current = price_maps[asset_id].get(date)
            if previous and current:
                daily_return += weight * (current / previous - 1.0)
        equity_curve.append({"date": date, "value": round(equity_curve[-1]["value"] * (1.0 + daily_return), 8)})

    if not allocations or not equity_curve:
        raise ValueError("insufficient history to run CURRENT_TAA")
    return {
        "model": MODEL_NAME,
        "model_description": MODEL_DESCRIPTION,
        "factor_definition": {
            "momentum_6m": 0.4,
            "momentum_12m": 0.3,
            "drawdown_resilience_12m": 0.3,
        },
        "period": {"start": equity_curve[0]["date"], "end": equity_curve[-1]["date"]},
        "asset_count": len(enabled),
        "assets": enabled,
        "metrics": build_metrics(equity_curve),
        "equity_curve": equity_curve,
        "monthly_allocations": allocations,
        "latest_index_target_weights": allocations[-1]["weights"],
    }


def build_metrics(curve: list[dict]) -> dict:
    returns = [current["value"] / previous["value"] - 1.0 for previous, current in zip(curve, curve[1:])]
    years = max(len(returns) / 252.0, 1.0 / 252.0)
    annual = (curve[-1]["value"] / curve[0]["value"]) ** (1.0 / years) - 1.0
    drawdown = _max_drawdown_values([row["value"] for row in curve])
    mean = sum(returns) / len(returns) if returns else 0.0
    variance = sum((value - mean) ** 2 for value in returns) / len(returns) if returns else 0.0
    sharpe = mean / sqrt(variance) * sqrt(252.0) if variance > 0 else 0.0
    return {"annual_return": round(annual, 6), "max_drawdown": round(drawdown, 6), "sharpe": round(sharpe, 6)}


def _max_drawdown_values(values: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst
