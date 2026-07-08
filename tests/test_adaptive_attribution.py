from engine.selection import compare_adaptive_selection_attribution


def test_adaptive_attribution_returns_sections():
    result = compare_adaptive_selection_attribution({"selection": -1.0}, {"selection": 0.5})

    assert {"baseline", "candidate", "static_factor", "adaptive_factor", "selection"} <= set(result)


def test_adaptive_attribution_calculates_improvement():
    result = compare_adaptive_selection_attribution({"selection": -1.0}, {"selection": 0.5})

    assert result["adaptive_factor"] == 1.5


def test_adaptive_attribution_flags_improved():
    result = compare_adaptive_selection_attribution({"selection": -1.0}, {"selection": 0.5})

    assert result["improved"] is True


def test_adaptive_attribution_flags_not_improved():
    result = compare_adaptive_selection_attribution({"selection": 1.0}, {"selection": 0.5})

    assert result["improved"] is False


def test_adaptive_attribution_uses_default_names():
    result = compare_adaptive_selection_attribution({}, {})

    assert result["candidate"] == "V8_ADAPTIVE_SELECTION"


def test_adaptive_attribution_accepts_custom_names():
    result = compare_adaptive_selection_attribution({}, {}, baseline="A", candidate="B")

    assert result["baseline"] == "A"
    assert result["candidate"] == "B"


def test_adaptive_attribution_supports_selection_contribution_key():
    result = compare_adaptive_selection_attribution(
        {"selection_contribution": -0.5},
        {"selection_contribution": 0.25},
    )

    assert result["adaptive_factor"] == 0.75


def test_adaptive_attribution_selection_payload_matches_top_level():
    result = compare_adaptive_selection_attribution({"selection": -1.0}, {"selection": 0.5})

    assert result["selection"]["improvement"] == result["adaptive_factor"]


def test_adaptive_attribution_rounds_values():
    result = compare_adaptive_selection_attribution({"selection": -1.11119}, {"selection": 0.22229})

    assert result["adaptive_factor"] == 1.3335


def test_adaptive_attribution_handles_missing_values():
    result = compare_adaptive_selection_attribution({}, {})

    assert result["adaptive_factor"] == 0.0
