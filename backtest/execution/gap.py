def build_execution_gap(research_overlap, execution):
    keys=("annual_return","max_drawdown","sharpe","calmar")
    return {f"{key}_gap":round(float(execution.get(key,0))-float(research_overlap.get(key,0)),6) for key in keys}
