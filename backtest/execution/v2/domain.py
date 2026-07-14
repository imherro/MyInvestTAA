from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


WEIGHT_TOLERANCE = 1e-8


@dataclass
class PortfolioSnapshot:
    date: str
    nav: float
    weights: dict[str, float]
    stale_valuation_assets: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RebalanceRequest:
    event_id: str
    signal_date: str
    scheduled_execution_date: str
    requested_target_weights: dict[str, float]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class InstrumentTarget:
    instrument_id: str
    target_weight: float
    executable: bool
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PendingAdjustment:
    adjustment_id: str
    parent_event_id: str
    instrument_id: str
    signal_date: str
    scheduled_execution_date: str
    target_weight: float
    pre_trade_weight: float
    deferred_weight_delta: float
    direction: Literal["increase", "reduce"]
    reason: str = "held_asset_missing_price"
    status: Literal["pending", "completed", "superseded"] = "pending"
    created_date: str = ""
    last_attempt_date: str = ""
    completed_date: str | None = None
    deferred_days: int | None = None
    superseded_by_signal_date: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionAttempt:
    adjustment_id: str
    instrument_id: str
    date: str
    status: str
    target_weight: float
    actual_weight: float

    def as_dict(self) -> dict:
        return {"event_type": "pending_adjustment_attempt", **asdict(self)}


@dataclass
class ExecutedAdjustment:
    instrument_id: str
    direction: Literal["buy", "sell", "unchanged"]
    pre_trade_value: float
    post_trade_value: float
    execution_date: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CostBreakdown:
    commission_cost: float = 0.0
    slippage_cost: float = 0.0
    tax_cost: float = 0.0
    total_cost: float = 0.0


@dataclass
class CashAccrual:
    date: str
    opening_cash: float
    accrued_interest: float = 0.0


@dataclass
class CostPolicy:
    policy_id: str = "B1_ZERO_COST"
    commission_bps: float = 0.0
    slippage_bps: float = 0.0


@dataclass
class CashYieldPolicy:
    policy_id: str = "B1_ZERO_CASH_YIELD"
    annualized_rate: float = 0.0
