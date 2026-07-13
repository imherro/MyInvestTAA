from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev


MIN_OVERLAP_DAYS = 500
MIN_CORRELATION = 0.65
MAX_TRACKING_ERROR = 0.30


def score_proxy_candidate(research_rows, candidate_rows) -> dict:
    research = {row.date: float(row.close) for row in research_rows}
    candidate = {row.date: float(row.close) for row in candidate_rows}
    dates = sorted(set(research) & set(candidate))
    if len(dates) < 2:
        return _empty_score(dates)
    research_returns = _returns(research, dates)
    candidate_returns = _returns(candidate, dates)
    overlap_days = len(research_returns)
    correlation = _correlation(research_returns, candidate_returns)
    differences = [left - right for left, right in zip(candidate_returns, research_returns)]
    tracking_error = pstdev(differences) * sqrt(252) if len(differences) > 1 else 0.0
    beta = _beta(research_returns, candidate_returns)
    research_annual = _annual_return(research_returns)
    candidate_annual = _annual_return(candidate_returns)
    return_gap = candidate_annual - research_annual
    drawdown_gap = _max_drawdown(candidate_returns) - _max_drawdown(research_returns)
    volatility_gap = _volatility(candidate_returns) - _volatility(research_returns)
    score = _score(correlation, tracking_error, drawdown_gap, return_gap, overlap_days)
    hard_gate_reasons = []
    if overlap_days < MIN_OVERLAP_DAYS: hard_gate_reasons.append("overlap_days_below_500")
    if correlation < MIN_CORRELATION: hard_gate_reasons.append("correlation_below_0.65")
    if tracking_error > MAX_TRACKING_ERROR: hard_gate_reasons.append("tracking_error_above_0.30")
    quality = "none" if overlap_days == 0 else ("medium" if not hard_gate_reasons else "low")
    return {"overlap_start": dates[1] if len(dates)>1 else None, "overlap_end": dates[-1] if dates else None, "overlap_days": overlap_days, "correlation": round(correlation,6), "tracking_error_annualized": round(tracking_error,6), "annual_return_gap": round(return_gap,6), "max_drawdown_gap": round(drawdown_gap,6), "volatility_gap": round(volatility_gap,6), "beta": round(beta,6), "score": round(score,6), "recommended_mapping_quality": quality, "hard_gate_reasons": hard_gate_reasons}


def _empty_score(dates):
    return {"overlap_start": None, "overlap_end": dates[-1] if dates else None, "overlap_days": 0, "correlation": 0.0, "tracking_error_annualized": 0.0, "annual_return_gap": 0.0, "max_drawdown_gap": 0.0, "volatility_gap": 0.0, "beta": 0.0, "score": 0.0, "recommended_mapping_quality": "none", "hard_gate_reasons": ["insufficient_overlap"]}


def _returns(prices, dates): return [prices[right] / prices[left] - 1 for left, right in zip(dates, dates[1:]) if prices[left] > 0]
def _correlation(left, right):
    if len(left)<2 or pstdev(left)==0 or pstdev(right)==0: return 0.0
    left_mean,right_mean=mean(left),mean(right)
    return sum((a-left_mean)*(b-right_mean) for a,b in zip(left,right))/(len(left)*pstdev(left)*pstdev(right))
def _beta(benchmark, asset):
    variance=pstdev(benchmark)**2
    benchmark_mean,asset_mean=mean(benchmark),mean(asset)
    return 0.0 if variance==0 else sum((a-benchmark_mean)*(b-asset_mean) for a,b in zip(benchmark,asset))/len(benchmark)/variance
def _annual_return(values): return (1+__import__('functools').reduce(lambda a,b:a*(1+b),values,1.0))**(252/len(values))-1 if values else 0.0
def _max_drawdown(values):
    level=peak=1.0; worst=0.0
    for value in values: level*=1+value; peak=max(peak,level); worst=min(worst,level/peak-1)
    return worst
def _volatility(values): return pstdev(values)*sqrt(252) if len(values)>1 else 0.0
def _score(correlation, tracking_error, drawdown_gap, return_gap, overlap_days):
    correlation_score=max(0,min(1,correlation)); te_score=max(0,1-tracking_error/.30); dd_score=max(0,1-abs(drawdown_gap)/.30); return_score=max(0,1-abs(return_gap)/.30); overlap_score=min(1,overlap_days/1000)
    return .40*correlation_score+.25*te_score+.15*dd_score+.10*return_score+.10*overlap_score
