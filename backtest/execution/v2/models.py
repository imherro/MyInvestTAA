from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionV2Config:
    strategy: str = "EXECUTION_PROXY_V2_EXPERIMENTAL"
    engine_status: str = "experimental_validation_only"
    commission_bps: float = 0.0
    slippage_bps: float = 0.0
    cash_yield: float = 0.0
