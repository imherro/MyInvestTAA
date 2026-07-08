from __future__ import annotations

from engine.selection.models import SelectionAttribution


def compare_selection_attribution(
    baseline_attribution: dict,
    candidate_attribution: dict,
    baseline: str = "V3_TREND_RISK_ADJUSTED",
    candidate: str = "V5_RELATIVE_STRENGTH_SELECTION",
) -> dict:
    old = round(float(baseline_attribution.get("selection", 0.0)), 4)
    new = round(float(candidate_attribution.get("selection", 0.0)), 4)
    improvement = round(new - old, 4)
    return SelectionAttribution(
        baseline=baseline,
        candidate=candidate,
        old=old,
        new=new,
        improvement=improvement,
        improved=improvement > 0,
    ).as_dict()
