from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.asset_repository import load_assets
from engine.taa_score import build_taa_ranking


app = FastAPI(
    title="MyInvestTAA",
    description="Tactical Asset Allocation MVP with drawdown and anchor scoring.",
    version="0.1.0",
)


@app.get("/api/assets")
def get_assets() -> list[dict]:
    return load_assets()


@app.get("/api/taa/ranking")
def get_taa_ranking() -> list[dict]:
    return build_taa_ranking(load_assets())


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    ranking = build_taa_ranking(load_assets())
    rows = "\n".join(
        f"""
        <tr>
          <td><strong>{item["name"]}</strong><span>{item["id"]}</span></td>
          <td>{item["category"]}</td>
          <td>{item["drawdown"]["current_drawdown_pct"]:.1f}%</td>
          <td>{item["drawdown_score"]:.1f}</td>
          <td>{item["anchor_score"]:.1f}<span>{item["anchor_level"]}</span></td>
          <td>{item["placeholder_score"]:.1f}</td>
          <td><strong>{item["taa_score"]:.1f}</strong></td>
          <td><span class="badge {item["recommendation"]}">{item["recommendation"]}</span></td>
        </tr>
        """
        for item in ranking
    )

    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyInvestTAA Dashboard</title>
      <style>
        :root {{
          color-scheme: light;
          --bg: #f6f7f9;
          --panel: #ffffff;
          --text: #1d2433;
          --muted: #5f6b7a;
          --line: #d8dee8;
          --accent: #2563eb;
          --good: #0f766e;
          --watch: #b45309;
          --risk: #b91c1c;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          background: var(--bg);
          color: var(--text);
          font-family: Arial, "Microsoft YaHei", sans-serif;
        }}
        header {{
          background: var(--panel);
          border-bottom: 1px solid var(--line);
          padding: 22px 32px 18px;
        }}
        main {{
          max-width: 1180px;
          margin: 0 auto;
          padding: 26px 24px 40px;
        }}
        h1 {{
          margin: 0 0 8px;
          font-size: 26px;
          font-weight: 700;
          letter-spacing: 0;
        }}
        p {{
          margin: 0;
          color: var(--muted);
          line-height: 1.6;
        }}
        .summary {{
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 14px;
          margin-bottom: 18px;
        }}
        .metric {{
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 16px;
        }}
        .metric label {{
          display: block;
          color: var(--muted);
          font-size: 13px;
          margin-bottom: 8px;
        }}
        .metric strong {{
          display: block;
          font-size: 22px;
        }}
        table {{
          width: 100%;
          border-collapse: collapse;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          overflow: hidden;
        }}
        th, td {{
          padding: 13px 14px;
          border-bottom: 1px solid var(--line);
          text-align: left;
          vertical-align: middle;
          font-size: 14px;
        }}
        th {{
          background: #eef2f7;
          color: #344054;
          font-weight: 700;
        }}
        td span {{
          display: block;
          color: var(--muted);
          font-size: 12px;
          margin-top: 4px;
        }}
        tr:last-child td {{ border-bottom: 0; }}
        .badge {{
          display: inline-block;
          min-width: 92px;
          padding: 5px 9px;
          border-radius: 999px;
          color: #fff;
          text-align: center;
          font-size: 12px;
          margin: 0;
        }}
        .overweight {{ background: var(--good); }}
        .watch_overweight {{ background: var(--accent); }}
        .neutral {{ background: var(--watch); }}
        .underweight, .avoid {{ background: var(--risk); }}
        @media (max-width: 820px) {{
          header {{ padding: 18px 18px 14px; }}
          main {{ padding: 18px 12px 28px; }}
          .summary {{ grid-template-columns: 1fr; }}
          table {{ display: block; overflow-x: auto; }}
          th, td {{ white-space: nowrap; }}
        }}
      </style>
    </head>
    <body>
      <header>
        <h1>MyInvestTAA Dashboard</h1>
        <p>Drawdown + Asset Anchor MVP. 输出为资产配置研究权重信号，不是交易指令。</p>
      </header>
      <main>
        <section class="summary" aria-label="summary">
          <div class="metric"><label>资产数量</label><strong>{len(ranking)}</strong></div>
          <div class="metric"><label>最高 TAA Score</label><strong>{ranking[0]["taa_score"]:.1f}</strong></div>
          <div class="metric"><label>服务端口</label><strong>8025</strong></div>
        </section>
        <table>
          <thead>
            <tr>
              <th>资产</th>
              <th>类别</th>
              <th>当前回撤</th>
              <th>回撤评分</th>
              <th>资产锚</th>
              <th>占位评分</th>
              <th>TAA Score</th>
              <th>配置状态</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </main>
    </body>
    </html>
    """


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8025, reload=False)

