"""Self-contained HTML performance report (no external dependencies).

Generates report.html with stats, an SVG equity curve, Monte Carlo
risk summary, and the full trade table.
"""
from __future__ import annotations

import html
from pathlib import Path

from . import montecarlo


def _equity_svg(rs: list[float], width: int = 860, height: int = 260) -> str:
    if not rs:
        return "<p>No closed trades.</p>"
    eq = [0.0]
    for r in rs:
        eq.append(eq[-1] + r)
    lo, hi = min(eq), max(eq)
    span = (hi - lo) or 1.0
    pad = 12
    n = len(eq)
    pts = []
    for i, v in enumerate(eq):
        x = pad + i * (width - 2 * pad) / max(n - 1, 1)
        y = height - pad - (v - lo) * (height - 2 * pad) / span
        pts.append(f"{x:.1f},{y:.1f}")
    zero_y = height - pad - (0 - lo) * (height - 2 * pad) / span
    return (
        f'<svg viewBox="0 0 {width} {height}" style="width:100%;background:#111">'
        f'<line x1="0" y1="{zero_y:.1f}" x2="{width}" y2="{zero_y:.1f}" '
        f'stroke="#444" stroke-dasharray="4 4"/>'
        f'<polyline fill="none" stroke="#e6b312" stroke-width="2" '
        f'points="{" ".join(pts)}"/></svg>'
    )


def generate(stats: dict, out_path: str | Path, period: str = "") -> Path:
    trades = stats.get("trade_list", [])
    closed = [t for t in trades if t.outcome in ("win", "loss")]
    rs = [t.result_r for t in closed]
    mc = montecarlo.simulate(rs) if len(rs) >= 10 else {"note": "too few trades"}

    stat_rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in stats.items() if k != "trade_list")
    mc_rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in mc.items())
    trade_rows = "".join(
        f"<tr><td>{t.signal.time}</td><td>{t.signal.direction}</td>"
        f"<td>{t.signal.confidence}</td><td>{t.signal.entry}</td>"
        f"<td>{t.signal.stop}</td><td>{t.signal.target}</td>"
        f"<td>{t.signal.rr}</td><td class='{t.outcome}'>{t.outcome}</td>"
        f"<td>{t.result_r:+.2f}</td></tr>" for t in trades)

    doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Gold Engine Report</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#181818;color:#ddd;
      max-width:920px;margin:24px auto;padding:0 16px}}
 h1,h2{{color:#e6b312}} table{{border-collapse:collapse;width:100%;margin:12px 0}}
 td,th{{border:1px solid #333;padding:6px 10px;font-size:14px;text-align:left}}
 tr:nth-child(even){{background:#1f1f1f}} .win{{color:#4caf50}} .loss{{color:#ef5350}}
 .expired{{color:#888}} .note{{color:#999;font-size:13px}}
</style></head><body>
<h1>Gold Engine — Performance Report</h1>
<p class="note">Period: {html.escape(period) or "full history"} ·
Walk-forward simulation, pessimistic fills, spread costs included.
R multiples are position-size agnostic. Past performance does not
guarantee future results.</p>
<h2>Equity curve (R)</h2>{_equity_svg(rs)}
<h2>Statistics</h2><table>{stat_rows}</table>
<h2>Monte Carlo (5,000 resampled paths)</h2><table>{mc_rows}</table>
<h2>Trades ({len(trades)})</h2>
<table><tr><th>signal time</th><th>dir</th><th>conf</th><th>entry</th>
<th>stop</th><th>target</th><th>RR</th><th>outcome</th><th>R</th></tr>
{trade_rows}</table>
</body></html>"""
    out = Path(out_path)
    out.write_text(doc, encoding="utf-8")
    return out
