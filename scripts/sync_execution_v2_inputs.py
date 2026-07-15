from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import tushare as ts


ROOT = Path(__file__).resolve().parents[1]
CALENDAR_PATH = ROOT / "data" / "market" / "cn_equity_trade_calendar.json"
METADATA_PATH = ROOT / "data" / "universe" / "execution_instrument_metadata.json"
EXECUTION_UNIVERSE = ROOT / "data" / "universe" / "china_execution_universe.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync verified Execution V2 calendar and ETF metadata.")
    parser.add_argument("--end", required=True, help="Latest complete market date in YYYY-MM-DD format.")
    args = parser.parse_args()
    end_date = args.end.replace("-", "")
    if len(end_date) != 8 or not end_date.isdigit():
        raise SystemExit("--end must use YYYY-MM-DD format")
    token = _token()
    client = ts.pro_api(token)
    calendar = client.trade_cal(
        exchange="SSE", start_date="20110101", end_date=end_date, is_open="1"
    ).sort_values("cal_date")
    funds = client.fund_basic(market="E")
    universe = json.loads(EXECUTION_UNIVERSE.read_text(encoding="utf-8"))
    ids = {row["asset_id"] for row in universe}
    selected = funds[funds["ts_code"].isin(ids)].copy()
    missing = sorted(ids - set(selected["ts_code"]))
    if missing:
        raise RuntimeError(f"Tushare fund_basic missing execution instruments: {missing}")

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    calendar_payload = {
        "schema_version": "1.0",
        "exchange": "SSE",
        "source": "tushare.trade_cal",
        "source_query": {"exchange": "SSE", "is_open": "1", "start_date": "20110101", "end_date": end_date},
        "generated_at": generated_at,
        "verified": True,
        "dates": [str(value) for value in calendar["cal_date"]],
    }
    metadata = []
    for row in selected.sort_values("ts_code").to_dict(orient="records"):
        listing_date = _date(row.get("list_date"))
        if not listing_date:
            raise RuntimeError(f"missing list_date for {row['ts_code']}")
        metadata.append(
            {
                "instrument_id": row["ts_code"],
                "name": row.get("name"),
                "listing_date": listing_date,
                "investable_start_date": listing_date,
                "investable_start_rule": "verified_listing_date_only_b1_no_liquidity_threshold",
                "price_return_basis": "qfq_market_price",
                "fund_expense_treatment": "embedded_in_price",
                "management_fee_rate": None,
                "custodian_fee_rate": None,
                "metadata_source": "tushare.fund_basic",
                "metadata_as_of": args.end,
                "verified": True,
            }
        )
    CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_PATH.write_text(json.dumps(calendar_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"calendar_days": len(calendar_payload["dates"]), "instrument_count": len(metadata)})


def _token() -> str:
    value = os.getenv("TUSHARE_TOKEN")
    env_path = ROOT / ".env"
    if not value and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("TUSHARE_TOKEN="):
                value = line.split("=", 1)[1].strip()
                break
    if not value:
        raise RuntimeError("TUSHARE_TOKEN is required")
    return value


def _date(value: object) -> str | None:
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


if __name__ == "__main__":
    main()
