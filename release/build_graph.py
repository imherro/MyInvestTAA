from __future__ import annotations

import hashlib
import json


BUILD_STEPS = (
    ("local_input_preflight", ()),
    ("strategy_diagnosis", ("local_input_preflight",)),
    ("v11_current_allocation", ("strategy_diagnosis",)),
    ("research_backtest_validation", ("local_input_preflight",)),
    ("execution_backtest_validation", ("research_backtest_validation",)),
    ("approval_integrity_verification", ("local_input_preflight",)),
    (
        "execution_aware_shadow_portfolio",
        ("research_backtest_validation", "execution_backtest_validation", "approval_integrity_verification"),
    ),
    (
        "current_market_decision",
        ("v11_current_allocation", "execution_aware_shadow_portfolio"),
    ),
    ("system_acceptance_report", ("current_market_decision",)),
    ("release_manifest", ("system_acceptance_report",)),
)


def dependency_graph() -> dict:
    return {
        "steps": [
            {"name": name, "dependencies": list(dependencies)}
            for name, dependencies in BUILD_STEPS
        ]
    }


def dependency_graph_hash() -> str:
    payload = json.dumps(
        dependency_graph(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
