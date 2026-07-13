from datetime import date

def drawdown_window(report):
    curve=report.get("equity_curve",[]);peak_value=curve[0]["value"];peak_date=curve[0]["date"];best=(0.0,peak_date,peak_date)
    for row in curve:
        if row["value"]>peak_value:peak_value=row["value"];peak_date=row["date"]
        drawdown=row["value"]/peak_value-1
        if drawdown<best[0]:best=(drawdown,peak_date,row["date"])
    recovery=next((row["date"] for row in curve if row["date"]>best[2] and row["value"]>=next(x["value"] for x in curve if x["date"]==best[1])),None)
    return {"max_drawdown":round(best[0],6),"start_date":best[1],"trough_date":best[2],"recovery_date":recovery,"duration_days":(date.fromisoformat(best[2])-date.fromisoformat(best[1])).days}
