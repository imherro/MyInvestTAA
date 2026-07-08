from __future__ import annotations


def compare_adaptive_selection_attribution(
    static_attribution: dict,
    adaptive_attribution: dict,
    baseline: str = "V7_STOCK_BREADTH_SELECTION",
    candidate: str = "V8_ADAPTIVE_SELECTION",
) -> dict:
    static_selection = _selection_value(static_attribution)
    adaptive_selection = _selection_value(adaptive_attribution)
    adaptive_factor = round(adaptive_selection - static_selection, 4)
    return {
        "baseline": baseline,
        "candidate": candidate,
        "static_factor": static_selection,
        "adaptive_factor": adaptive_factor,
        "improved": adaptive_factor > 0.0,
        "selection": {
            "old": static_selection,
            "new": adaptive_selection,
            "improvement": adaptive_factor,
            "improved": adaptive_factor > 0.0,
        },
    }


def _selection_value(attribution: dict) -> float:
    value = attribution.get("selection", attribution.get("selection_contribution", 0.0))
    return round(float(value), 4)
