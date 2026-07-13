from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionBacktestConfig:
    strategy: str = "EXECUTION_PROXY_MVP"
    allow_low_quality_proxy: bool = False
    min_mapped_coverage: float = 0.70

@dataclass(frozen=True)
class ExecutionPrice:
    asset_id: str
    date: str
    close: float
    return_basis: str = "qfq"
    def as_dict(self): return {"date": self.date, "close": self.close, "return_basis": self.return_basis}
