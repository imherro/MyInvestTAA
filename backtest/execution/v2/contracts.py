from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SourceManifestEntry:
    """Caller-supplied provenance; the execution core never opens this path."""

    logical_name: str
    path: str
    sha256: str
    role: str


@dataclass(frozen=True)
class ExecutionCoreConfig:
    """Stable zero-cost core configuration contract."""

    strategy_id: str = "EXECUTION_PROXY_V2_CORE"
    engine_status: str = "core_candidate"
    schema_version: str = "1.0"


@dataclass(frozen=True)
class ExecutionCoreInputs:
    """In-memory inputs for the future C0-B core entry point."""

    research_report: Mapping[str, Any]
    execution_price_data: Mapping[str, Sequence[Any]]
    approved_mappings: Sequence[Any]
    execution_universe: Sequence[Any]
    trade_calendar: Mapping[str, Any]
    instrument_metadata: Mapping[str, Any]
    source_manifest: tuple[SourceManifestEntry, ...]
    config: ExecutionCoreConfig = ExecutionCoreConfig()


@dataclass(frozen=True)
class ExecutionCoreResult:
    """V1-independent result contract; serialization is an outer-layer concern."""

    core_run_id: str
    periods: Mapping[str, Any]
    equity_curve: tuple[Mapping[str, Any], ...]
    daily_states: tuple[Mapping[str, Any], ...]
    signal_events: tuple[Mapping[str, Any], ...]
    pending_adjustments: tuple[Mapping[str, Any], ...]
    investability_timeline: tuple[Mapping[str, Any], ...]
    coverage_contract: Mapping[str, Any]
    gap_metrics: Mapping[str, Any]
    source_manifest: tuple[SourceManifestEntry, ...]
    validation: Mapping[str, Any]


@dataclass(frozen=True)
class ExecutionVersionStatus:
    """Lifecycle status shared by documentation and future adapters."""

    version: str
    lifecycle_status: str
    semantics: str
    production_actionable: bool
    current_formal_gate_source: bool
    current_decision_member: bool
    release_gate_member: bool
    maintenance_mode: str
    baseline_output_set_hash: str | None = None
