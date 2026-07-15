from backtest.research.candidate import (
    ResearchCandidateSpec,
    build_v12_candidate_report,
)


def test_v12_spec_is_shadow_only_and_contains_free_cash_flow():
    spec = ResearchCandidateSpec.load()
    assert spec.strategy_id == "V12_EXPANDED_UNIVERSE_CANDIDATE"
    assert spec.added_asset_id == "480092.CNI"
    assert spec.production_actionable is False


def test_v12_report_preserves_v11_boundary():
    spec = ResearchCandidateSpec.load()
    report = build_v12_candidate_report(
        spec,
        {
            "strategy": spec.strategy_id,
            "universe_count": 14,
            "universe_scope": {"included_asset_ids": ["480092.CNI"]},
            "period": {"start": "2021-01-01", "end": "2026-01-01"},
            "metrics": {},
        },
        {"added_asset_id": "480092.CNI"},
        {"decision": {"ready_for_execution_validation": False}},
    )
    assert report["available"] is True
    assert report["production_actionable"] is False
    assert "does not replace V11" in report["relationship_to_v11"]
