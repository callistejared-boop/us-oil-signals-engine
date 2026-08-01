"""Public track record — the sellable asset.

Generates track_record.html from the live journal: EVERY signal ever logged
(wins, losses, scratches, open — nothing hidden), an equity curve in R, and
the summary stats a prospective subscriber should demand. Timestamped and
regenerated automatically each hour by the pipeline, so the record can't be
cherry-picked after the fact.

Design choices that make it credible:
  * losses shown as prominently as wins;
  * R multiples, not dollar amounts (honest and account-size independent);
  * win-rate displayed next to expectancy so it can't mislead;
  * the paper/live phase of each period is labelled;
  * inline SVG equity curve (no external JS -> loads anywhere, easy to host).
"""
import html
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from engine import store, markets  # noqa: E402

OUT = ROOT / "track_record.html"
FWD_START = "2026-07-17"   # forward-test window start (paper phase begins)
FOCUS_SYMBOL = "WTIUSD"    # page is branded "US Oil Signals" - must show ONLY
                           # WTI trades, not legacy pre-pivot multi-market history


def _equity_svg(rs, w=860, h=220, pad=30):
    """Inline SVG cumulative-R curve."""
    if not rs:
        return "<p class='muted'>No closed trades yet.</p>"
    cum, ys = 0.0, [0.0]
    for r in rs:
        cum += r
        ys.append(cum)
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1.0
    n = len(ys)
    pts = []
    for i, y in enumerate(ys):
        px = pad + (w - 2 * pad) * (i / max(n - 1, 1))
        py = h - pad - (h - 2 * pad) * ((y - lo) / span)
        pts.append(f"{px:.1f},{py:.1f}")
    zero_y = h - pad - (h - 2 * pad) * ((0 - lo) / span)
    color = "#38c172" if ys[-1] >= 0 else "#e0526a"
    return (f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='Equity curve in R'>"
            f"<line x1='{pad}' y1='{zero_y:.1f}' x2='{w-pad}' y2='{zero_y:.1f}' "
            f"stroke='#39424f' stroke-dasharray='4 4'/>"
            f"<polyline points='{' '.join(pts)}' fill='none' stroke='{color}' "
            f"stroke-width='2.5'/>"
            f"<text x='{pad}' y='16' fill='#8b93a3' font-size='12'>cumulative R "
            f"(latest {ys[-1]:+.1f}R)</text></svg>")


def build(rows=None, symbol=FOCUS_SYMBOL):
    rows = rows if rows is not None else store.load_array(ROOT / "trades.json")
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    rows = sorted(rows, key=lambda r: str(r.get("opened", "")))
    closed = [r for r in rows if r.get("status") in ("win", "loss", "scratch")]
    rs = [float(r.get("result_r", 0) or 0) for r in closed]
    n = len(rs)
    wins = sum(1 for x in rs if x > 1e-9)
    exp = (sum(rs) / n) if n else 0.0
    gross_w = sum(x for x in rs if x > 0)
    gross_l = abs(sum(x for x in rs if x < 0))
    pf = "inf" if (gross_w and not gross_l) else (f"{gross_w/gross_l:.2f}" if gross_l else "0")
    open_rows = [r for r in rows if r.get("status") == "open"]

    trs = ""
    for r in reversed(rows[-400:]):
        status = r.get("status", "?")
        cls = {"win": "win", "loss": "loss", "open": "open"}.get(status, "flat")
        res = f"{float(r.get('result_r', 0) or 0):+.2f}R" if status in ("win", "loss", "scratch") else "…"
        phase = "paper" if str(r.get("opened", ""))[:10] >= FWD_START else "pre-record"
        trs += ("<tr><td>" + html.escape(str(r.get("opened", ""))[:16]) + "</td>"
                "<td>" + html.escape(markets.name(r.get("symbol", "?"))) + "</td>"
                "<td>" + html.escape(str(r.get("direction", "?")).upper()) + "</td>"
                f"<td>{r.get('entry','')}</td><td>{r.get('stop','')}</td>"
                f"<td>{r.get('target','')}</td>"
                f"<td class='{cls}'>{html.escape(status)}</td>"
                f"<td class='{cls}'>{res}</td><td class='muted'>{phase}</td></tr>")

    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = f"""<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>US Oil Signals — Verified Track Record</title><style>
body{{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:#0b0e14;
color:#e7eaf0;max-width:960px;margin:20px auto;padding:0 14px}}
h1{{color:#e6b312;font-size:24px}} .muted{{color:#8b93a3;font-size:13px}}
.kpis{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}}
.kpi{{background:#141a24;border:1px solid #232c3a;border-radius:10px;
padding:10px 16px;min-width:120px}}
.kpi b{{display:block;font-size:20px}} .kpi span{{color:#8b93a3;font-size:11px;
text-transform:uppercase;letter-spacing:.5px}}
table{{width:100%;border-collapse:collapse;background:#141a24;border:1px solid
#232c3a;border-radius:10px;overflow:hidden;font-size:12.5px;margin-top:10px}}
th,td{{padding:7px 9px;text-align:left;border-bottom:1px solid #202836}}
th{{background:#0f131b;color:#8b93a3;font-size:10.5px;text-transform:uppercase}}
.win{{color:#38c172;font-weight:600}} .loss{{color:#e0526a;font-weight:600}}
.open{{color:#5aa9ff}} .flat{{color:#8b93a3}}
.note{{background:#141a24;border:1px solid #2a3550;border-radius:10px;
padding:12px 16px;font-size:13px;line-height:1.5;margin:14px 0}}
svg{{width:100%;height:auto;background:#0f131b;border:1px solid #232c3a;
border-radius:10px}}</style></head><body>
<h1>US Oil Signals — Verified Track Record</h1>
<p class='muted'>Every US Oil (WTI) signal the engine has ever published —
wins, losses and open trades alike. Auto-generated {gen}. Results in R
multiples (1R = the amount risked). Forward-test (paper) phase began
{FWD_START}. WTI-only: earlier multi-market history (gold/forex/crypto) from
before the platform's WTI-only pivot is excluded — this page is exactly what
a US Oil subscriber would have seen.</p>
<div class='kpis'>
<div class='kpi'><b>{n}</b><span>closed trades</span></div>
<div class='kpi'><b>{(wins/n*100 if n else 0):.0f}%</b><span>win rate</span></div>
<div class='kpi'><b>{exp:+.2f}R</b><span>expectancy / trade</span></div>
<div class='kpi'><b>{sum(rs):+.1f}R</b><span>net result</span></div>
<div class='kpi'><b>{pf}</b><span>profit factor</span></div>
<div class='kpi'><b>{len(open_rows)}</b><span>open now</span></div>
</div>
{_equity_svg(rs)}
<div class='note'><b>How to read this honestly:</b> a professional system loses
often — the question is whether winners outsize losers (expectancy&nbsp;&gt;&nbsp;0).
Win-rate alone is marketing; expectancy is money. Trades are managed
mechanically: stop to break-even at +1R, 50% banked at +2R, runner to target.
Past results never guarantee future performance.</div>
<table><tr><th>opened (UTC)</th><th>market</th><th>dir</th><th>entry</th>
<th>stop</th><th>target</th><th>status</th><th>result</th><th>phase</th></tr>
{trs}</table>
<p class='muted'>Research/education only — not financial advice. Signals are
published to Telegram in real time before outcomes are known; this page is
regenerated automatically from the same journal that scores them.</p>
</body></html>"""
    return doc, {"n": n, "exp": round(exp, 3), "net": round(sum(rs), 2)}


def main():
    doc, kpi = build()
    OUT.write_text(doc, encoding="utf-8")
    print(f"track_record.html written — {kpi['n']} closed, "
          f"exp {kpi['exp']:+.2f}R, net {kpi['net']:+.1f}R")


if __name__ == "__main__":
    main()
