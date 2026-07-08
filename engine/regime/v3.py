from __future__ import annotations


def detect_market_regime_v3(price_series: list[dict], breadth: float | None = None) -> dict:
    closes = [float(row["close"]) for row in price_series]
    if len(closes) < 6:
        return {
            "state": "neutral",
            "confidence": 0.4,
            "evidence": ["insufficient history"],
            "trend_score": 0.0,
            "momentum": 0.0,
            "breadth": breadth,
            "volatility_state": "unknown",
        }
    current = closes[-1]
    ma3 = sum(closes[-3:]) / 3
    ma6 = sum(closes[-6:]) / 6
    momentum = current / closes[-6] - 1.0 if closes[-6] > 0 else 0.0
    volatility = _volatility(closes[-6:])
    evidence: list[str] = []
    trend_score = 0.0
    if current >= ma3 >= ma6:
        trend_score += 0.45
        evidence.append("MA trend positive")
    if momentum > 0:
        trend_score += 0.25
        evidence.append("momentum positive")
    if breadth is not None and breadth >= 0.55:
        trend_score += 0.15
        evidence.append("breadth supportive")
    if volatility < 0.08:
        trend_score += 0.15
        evidence.append("volatility contained")
    if trend_score >= 0.7:
        state = "bull"
    elif trend_score >= 0.45:
        state = "neutral"
    elif momentum < -0.1:
        state = "bear"
    else:
        state = "bull_caution"
    return {
        "state": state,
        "confidence": round(max(0.4, min(0.9, trend_score)), 4),
        "evidence": evidence or ["mixed trend evidence"],
        "trend_score": round(trend_score, 4),
        "momentum": round(momentum, 4),
        "breadth": breadth,
        "volatility_state": "low" if volatility < 0.08 else "high",
    }


def _volatility(values: list[float]) -> float:
    returns = [
        current / previous - 1.0
        for previous, current in zip(values, values[1:])
        if previous > 0
    ]
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / len(returns)
    return variance ** 0.5
