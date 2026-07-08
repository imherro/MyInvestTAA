from __future__ import annotations

from data.models import AssetMetadata, PriceBar


class BaoStockProvider:
    name = "baostock"

    def get_price_history(
        self,
        asset_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        return self._query_history(asset_id, start=start, end=end)

    def get_index_history(
        self,
        index_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        return self._query_history(index_id, start=start, end=end)

    def get_etf_list(self) -> list[AssetMetadata]:
        return []

    def provider_status(self) -> dict:
        return {
            "name": self.name,
            "available": False,
            "mode": "reserved_adapter",
            "requires": ["baostock"],
        }

    def _query_history(
        self,
        asset_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        try:
            import baostock as bs
        except ImportError as exc:
            raise RuntimeError("baostock package is not installed") from exc

        login = bs.login()
        if getattr(login, "error_code", "0") != "0":
            raise RuntimeError(f"baostock login failed: {login.error_msg}")
        try:
            result = bs.query_history_k_data_plus(
                _to_baostock_code(asset_id),
                "date,open,high,low,close,volume",
                start_date=start or "1990-01-01",
                end_date=end or "",
                frequency="d",
                adjustflag="2",
            )
            rows = []
            while result.next():
                rows.append(result.get_row_data())
            fields = result.fields
        finally:
            bs.logout()

        bars = []
        for values in rows:
            row = dict(zip(fields, values))
            if not row.get("close"):
                continue
            bars.append(
                PriceBar(
                    asset_id=asset_id,
                    date=row["date"],
                    open=_optional_float(row.get("open")),
                    high=_optional_float(row.get("high")),
                    low=_optional_float(row.get("low")),
                    close=float(row["close"]),
                    volume=_optional_float(row.get("volume")),
                    source=self.name,
                )
            )
        return bars


def _to_baostock_code(asset_id: str) -> str:
    if asset_id.startswith(("sh.", "sz.")):
        return asset_id
    prefix = "sh" if asset_id.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}.{asset_id.split('.')[0]}"


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
