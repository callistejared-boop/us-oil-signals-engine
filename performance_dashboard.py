"""Live performance dashboard — reads the trade journal (trades.json) and
writes dashboard.html: equity curve, headline stats, drawdown, consecutive
losses, per-pair, per-session, confidence-vs-outcome, and monthly returns,
each with a plain-English explanation. Re-run anytime for fresh numbers.
"""
import html
import json
import pathlib
from collections import defaultdict
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
import sys as _sys
_sys.path.insert(0, str(ROOT))
from engine import store as _store
rows = _store.load_array(ROOT / "trades.json")

closed = [r for r in rows if r.get("status") in ("win", "loss", "scratch")]


def session_of(iso):
    try:
        h = datetime.fromisoformat(iso).hour
    except Exception:  # noqa: BLE001
        return "unknown"
    if 7 <= h < 12:
        return "London"
    if 12 <= h < 21:
        return "New York"
    if 21 <= h or h < 7:
        return "Asian"
    return "off"


def block(rs):
    """Compute a stats block from a list of result_r values."""
    n = len(rs)
    if n == 0:
        return None
    wins = [x for x in rs if x > 1e-9]
    losses = [x for x in rs if x < -1e-9]
    gw = sum(wins)
    gl = abs(sum(losses))
    eq = []
    c = 0.0
    for x in rs:
        c += x
        eq.append(c)
    peak = eq[0]
    dd = 0.0
    for v in eq:
        peak = max(peak, v)
        dd = min(dd, v - peak)
    streak = mx = 0
    for x in rs:
        streak = streak + 1 if x < -1e-9 else 0
        mx = max(mx, streak)
    return {
        "n": n, "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / n,
        "pf": (gw / gl) if gl else float("inf"),
        "exp": sum(rs) / n, "net": sum(rs), "dd": dd, "maxloss": mx,
    }


allr = [r["result_r"] for r in closed]
overall = block(allr) or {"n": 0}

# equity curve points
eq = []
c = 0.0
for r in closed:
    c += r["result_r"]
    eq.append(c)

# groupings
by_sym = defaultdict(list)
by_sess = defaultdict(list)
by_month = defaultdict(list)
by_conf = defaultdict(list)
for r in closed:
    by_sym[r.get("symbol", "XAUUSD")].append(r["result_r"])
    by_sess[session_of(r.get("opened", ""))].append(r["result_r"])
    by_month[str(r.get("opened", ""))[:7]].append(r["result_r"])
    cf = int(r.get("confidence", 0))
    bucket = "90-95" if cf >= 90 else "80-89" if cf >= 80 else "70-79" if cf >= 70 else "<70"
    by_conf[bucket].append(r["result_r"])


def equity_svg(points, w=880, h=240):
    if not points:
        return "<p class='muted'>No closed trades yet — the curve fills in as trades settle.</p>"
    lo, hi = min(points + [0]), max(points + [0])
    span = (hi - lo) or 1
    pad = 10
    pts = []
    for i, v in enumerate(points):
        x = pad + i * (w - 2 * pad) / max(len(points) - 1, 1)
        y = h - pad - (v - lo) * (h - 2 * pad) / span
        pts.append(f"{x:.1f},{y:.1f}")
    zy = h - pad - (0 - lo) * (h - 2 * pad) / span
    color = "#38c172" if points[-1] >= 0 else "#e0526a"
    return (f"<svg viewBox='0 0 {w} {h}' style='width:100%;background:#0f131b;border-radius:10px'>"
            f"<line x1='0' y1='{zy:.1f}' x2='{w}' y2='{zy:.1f}' stroke='#2a3242' stroke-dasharray='4 4'/>"
            f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{' '.join(pts)}'/></svg>")


def pct(x):
    return f"{x*100:.0f}%"


def rr(x):
    return f"{x:+.1f}R"


def pf_fmt(x):
    return "∞" if x == float("inf") else f"{x:.2f}"


def table(title, explain, groups, order=None):
    keys = order or sorted(groups.keys())
    body = ""
    for k in keys:
        if k not in groups:
            continue
        b = block(groups[k])
        if not b:
            continue
        body += (f"<tr><td>{html.escape(str(k))}</td><td>{b['n']}</td>"
                 f"<td>{pct(b['win_rate'])}</td><td>{pf_fmt(b['pf'])}</td>"
                 f"<td class='{'pos' if b['net']>=0 else 'neg'}'>{rr(b['net'])}</td>"
                 f"<td>{b['exp']:+.2f}R</td></tr>")
    return (f"<h2>{title}</h2><p class='exp'>{explain}</p>"
            f"<table><tr><th>{title.split()[0]}</th><th>Trades</th><th>Win rate</th>"
            f"<th>Profit factor</th><th>Net</th><th>Expectancy</th></tr>{body}</table>")


tiles = ""
if overall.get("n"):
    for label, val, ex in [
        ("Trades", str(overall["n"]), "Total settled trades in the record."),
        ("Win rate", pct(overall["win_rate"]), "Share of trades that closed positive. 40–55% is normal and profitable at this reward-to-risk."),
        ("Profit factor", pf_fmt(overall["pf"]), "Gross profit ÷ gross loss. Above 1 is profitable; above 1.5 is strong."),
        ("Expectancy", f"{overall['exp']:+.2f}R", "Average R earned per trade. Positive = edge."),
        ("Net", rr(overall["net"]), "Total R banked. At 1% risk/trade, 1R ≈ 1% of account."),
        ("Max drawdown", rr(overall["dd"]), "Worst peak-to-valley dip. Size your risk so you can sit through this."),
        ("Max consec. losses", str(overall["maxloss"]), "Longest losing streak. These WILL happen — plan for them."),
    ]:
        tiles += (f"<div class='tile'><div class='k'>{label}</div>"
                  f"<div class='v'>{val}</div><div class='x'>{ex}</div></div>")
else:
    tiles = "<div class='tile'><div class='v'>No closed trades yet</div><div class='x'>The dashboard fills in automatically as signals settle.</div></div>"

doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Signals — Live Performance</title><style>
body{{font-family:-apple-system,"Segoe UI",system-ui,sans-serif;background:#0b0e14;color:#e7eaf0;max-width:960px;margin:20px auto;padding:0 16px}}
h1{{color:#e6b312}} h2{{color:#e6b312;font-size:18px;margin:26px 0 4px}}
.muted,.exp,.x{{color:#8b93a3}} .exp{{font-size:13px;margin:0 0 10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0}}
.tile{{background:#141a24;border:1px solid #232c3a;border-radius:12px;padding:14px}}
.tile .k{{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#8b93a3}}
.tile .v{{font-size:24px;font-weight:800;margin:4px 0}} .tile .x{{font-size:11px;line-height:1.4}}
table{{width:100%;border-collapse:collapse;background:#141a24;border:1px solid #232c3a;border-radius:10px;overflow:hidden;margin-bottom:8px}}
th,td{{padding:9px 11px;text-align:left;font-size:13px;border-bottom:1px solid #202836}}
th{{background:#0f131b;color:#8b93a3;font-size:11px;text-transform:uppercase}}
.pos{{color:#38c172;font-weight:700}} .neg{{color:#e0526a;font-weight:700}}
.disc{{background:#1a1608;border:1px solid #3a3113;border-radius:10px;padding:12px 14px;font-size:12px;color:#d8c58c;margin-top:20px}}
</style></head><body>
<h1>XAUUSD Signals — Live Performance</h1>
<p class="muted">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · reads your live trade journal · {overall.get('n',0)} settled trades.</p>
<div class="grid">{tiles}</div>
<h2>Equity curve (R)</h2>
<p class="exp">Cumulative R over time. Trade management (break-even + partials) is what keeps the slope steady instead of jagged.</p>
{equity_svg(eq)}
{table("Pair performance", "Which markets are actually carrying the edge. Cut or size down the laggards.", by_sym)}
{table("Session performance", "When your setups work best (times in UTC). London 07–12, New York 12–21, Asian 21–07.", by_sess, order=["London","New York","Asian","off","unknown"])}
{table("Confidence vs outcome", "Does a higher confidence score actually mean a higher win rate? If yes, the score is honest — trust it more when sizing.", by_conf, order=["90-95","80-89","70-79","<70"])}
{table("Monthly returns", "Net R per month — consistency matters more than any single big month.", by_month)}
<div class="disc">⚠️ These are live-tracked results on the engine's data feed (gold uses a futures proxy). The sample is still young — treat it as evidence building, not proof. Research/education only, not financial advice. Past results don't guarantee future outcomes.</div>
</body></html>"""

(ROOT / "dashboard.html").write_text(doc, encoding="utf-8")
print("wrote dashboard.html with", overall.get("n", 0), "trades")
