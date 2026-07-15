from __future__ import annotations

from collections import defaultdict


def map_index_weights(
    index_weights: dict[str, float],
    assets: list[dict],
    mappings: list[dict],
    etf_prices: dict[str, list[dict]],
    as_of_date: str,
    *,
    require_exact_date: bool = False,
) -> dict:
    asset_by_id = {asset["asset_id"]: asset for asset in assets}
    mapping_by_asset = {
        row["research_asset_id"]: row for row in mappings if row.get("enabled") is True
    }
    etf_weights: dict[str, float] = defaultdict(float)
    etf_details: dict[str, dict] = {}
    cash = float(index_weights.get("CASH", 0.0))
    cash_reasons = []

    for asset_id, weight_value in index_weights.items():
        if asset_id == "CASH":
            continue
        weight = float(weight_value)
        asset_name = asset_by_id.get(asset_id, {}).get("name", asset_id)
        mapping = mapping_by_asset.get(asset_id)
        if mapping is None:
            cash += weight
            cash_reasons.append({"research_asset_id": asset_id, "research_asset_name": asset_name, "weight": weight, "reason": "没有启用的ETF映射"})
            continue
        etf_id = mapping["etf_id"]
        rows = etf_prices.get(etf_id, [])
        valid_rows = [row for row in rows if row["date"] <= as_of_date and float(row["close"]) > 0]
        has_price = bool(valid_rows) and (not require_exact_date or valid_rows[-1]["date"] == as_of_date)
        if not has_price:
            cash += weight
            cash_reasons.append({"research_asset_id": asset_id, "research_asset_name": asset_name, "weight": weight, "reason": f"{etf_id}在{as_of_date}没有有效前复权价格"})
            continue
        etf_weights[etf_id] += weight
        detail = etf_details.setdefault(
            etf_id,
            {
                "etf_id": etf_id,
                "etf_name": mapping["etf_name"],
                "weight": 0.0,
                "mapping_quality": mapping["mapping_quality"],
                "notes": [],
                "research_assets": [],
            },
        )
        detail["weight"] += weight
        detail["notes"].append(mapping["notes"])
        detail["research_assets"].append({"asset_id": asset_id, "name": asset_name, "weight": round(weight, 10)})

    normalized = {etf_id: round(weight, 10) for etf_id, weight in etf_weights.items()}
    if cash > 1e-10:
        normalized["CASH"] = round(cash, 10)
    for detail in etf_details.values():
        detail["weight"] = round(detail["weight"], 10)
        detail["notes"] = list(dict.fromkeys(detail["notes"]))
    total = sum(normalized.values())
    return {
        "as_of_date": as_of_date,
        "weights": normalized,
        "etfs": sorted(etf_details.values(), key=lambda row: row["etf_id"]),
        "cash_weight": round(cash, 10),
        "cash_reasons": cash_reasons,
        "weight_sum": round(total, 10),
        "weight_sum_valid": abs(total - 1.0) <= 1e-8,
    }


def build_current_allocation(
    research: dict,
    assets: list[dict],
    mappings: list[dict],
    etf_prices: dict[str, list[dict]],
) -> dict:
    latest = research["monthly_allocations"][-1]
    mapped = map_index_weights(
        latest["weights"],
        assets,
        mappings,
        etf_prices,
        research["period"]["end"],
        require_exact_date=True,
    )
    asset_by_id = {asset["asset_id"]: asset for asset in assets}
    index_targets = [
        {
            "asset_id": asset_id,
            "name": "现金" if asset_id == "CASH" else asset_by_id[asset_id]["name"],
            "weight": weight,
        }
        for asset_id, weight in latest["weights"].items()
    ]
    return {
        "model": research["model"],
        "decision_date": latest["signal_date"],
        "effective_date": latest["effective_date"],
        "data_as_of": research["period"]["end"],
        "index_target_weights": index_targets,
        "etf_target_weights": mapped["etfs"],
        "cash_weight": mapped["cash_weight"],
        "cash_reasons": mapped["cash_reasons"],
        "weight_sum": mapped["weight_sum"],
        "weight_sum_valid": mapped["weight_sum_valid"],
        "trading_instruction": False,
    }
