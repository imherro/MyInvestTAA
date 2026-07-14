from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


WEIGHT_TOLERANCE = 1e-8
VALUE_TOLERANCE = 5e-10
COST_TOLERANCE = 1e-12
ZERO_POSITION_TOLERANCE = 1e-12
SERIALIZATION_DECIMALS = 10


@dataclass
class CostPolicy:
    policy_id: str
    scenario_id: str
    effective_date: str
    commission_buy_bps: float
    commission_sell_bps: float
    slippage_buy_bps: float
    slippage_sell_bps: float
    tax_buy_bps: float
    tax_sell_bps: float
    assumption_source: str
    evidence_status: str
    production_approved: bool
    policy_sha256: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutedAdjustment:
    adjustment_id: str
    sequence_number: int
    parent_event_id: str
    pending_adjustment_id: str | None
    instrument_id: str
    execution_date: str
    direction: Literal["buy", "sell"]
    pre_trade_value: float
    requested_post_trade_value: float
    executed_post_trade_value: float
    gross_traded_notional: float
    commission_cost: float
    slippage_cost: float
    tax_cost: float
    total_cost: float
    pre_trade_cash: float
    post_trade_cash: float
    event_pre_trade_nav: float
    event_post_trade_nav: float
    status: str
    mapping_quality: str
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)
