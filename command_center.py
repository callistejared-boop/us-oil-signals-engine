"""Unified Command Center - one screen for the whole platform.

Merges: live news-bias strip (BUY/SELL per pair), engine-health verdict,
headline performance, equity curve, what-predicts-wins attribution, latest
signal note, and quick links to every tool. Reads the live journal + the news
feed. Self-contained (stdlib only). Re-run anytime.
"""
import html
import json
import pathlib
import sys
from collections import defaultdict
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    from engine import fundamentals_feed as ff
except Exception:  # noqa: BLE001
    ff = None
try:
    from engine import store as _store
except Exception:  # noqa: BLE001
    _store = None


def load_json(name, default):
    p = ROOT / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


rows = _store.load_array(ROOT / "trades.json") if _store else load_json("trades.json", [])
closed = [r for r in rows if r.get("status") in ("win", "loss", "scratch")]


def session_of(iso):
    try:
        h = datetime.fromisoformat(iso).hour
    except Exception:  # noqa: BLE001
        return "unknown"
    return "London" if 7 <= h < 12 else "New York" if 12 <= h < 21 else "Asian"


def conf_bucket(c):
    c = int(c or 0)
    return "90-95" if c >= 90 else "80-89" if c >= 80 else "70-79" if c >= 70 else "<70"


def block(rs):
    n = len(rs)
    if not n:
        return None
    wins = [x for x in rs if x > 1e-9]
    losses = [x for x in rs if x < -1e-9]
    gw, gl = sum(wins), abs(sum(losses))
    eq, c = [], 0.0
    for x in rs:
        c += x
        eq.append(c)
    peak, dd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        dd = min(dd, v - peak)
    streak = mx = 0
    for x in rs:
        streak = streak + 1 if x < -1e-9 else 0
        mx = max(mx, streak)
    return {"n": n, "wins": len(wins), "wr": len(wins) / n,
            "pf": (gw / gl) if gl else float("inf"),
            "exp": sum(rs) / n, "net": sum(rs), "dd": dd, "maxloss": mx}


allr = [r["result_r"] for r in closed]
overall = block(allr) or {"n": 0}

by_sym, by_sess, by_conf, by_month = (defaultdict(list) for _ in range(4))
for r in closed:
    by_sym[r.get("symbol", "?")].append(r["result_r"])
    by_sess[session_of(r.get("opened", ""))].append(r["result_r"])
    by_conf[conf_bucket(r.get("confidence"))].append(r["result_r"])
    by_month[str(r.get("opened", ""))[:7]].append(r["result_r"])

# ---- engine-health checks -------------------------------------------------
health = []
cb = {k: block(v) for k, v in by_conf.items()}
order = [b for b in ["90-95", "80-89", "70-79"] if b in cb]
if len(order) >= 2:
    hi, lo = cb[order[0]]["wr"], cb[order[-1]]["wr"]
    if lo > hi + 0.05:
        health.append(("warn", "Confidence not calibrated",
                       f"Top bucket {order[0]} wins {hi*100:.0f}% vs {order[-1]} at {lo*100:.0f}% - "
                       f"inverted. Sample young ({overall['n']} trades); monitor, don't rewire."))
    elif hi > lo + 0.05:
        health.append(("ok", "Confidence is predictive",
                       f"{order[0]} wins {hi*100:.0f}% vs {order[-1]} {lo*100:.0f}% - trust it more."))
    else:
        health.append(("neutral", "Confidence roughly flat", "Not separating winners yet."))
if overall.get("n"):
    if overall["exp"] > 0:
        health.append(("ok", "Positive expectancy",
                       f"+{overall['exp']:.2f}R per trade across {overall['n']} trades "
                       f"(PF {overall['pf']:.2f})."))
    else:
        health.append(("warn", "Expectancy negative", "Review before sizing up."))
    sym_blocks = {k: block(v) for k, v in by_sym.items() if len(v) >= 5}
    if sym_blocks:
        worst = min(sym_blocks.items(), key=lambda kv: kv[1]["exp"])
        best = max(sym_blocks.items(), key=lambda kv: kv[1]["exp"])
        health.append(("neutral", "Market spread",
                       f"'{best[0]}' leads (exp {best[1]['exp']:+.2f}R); "
                       f"'{worst[0]}' lags (exp {worst[1]['exp']:+.2f}R, n={worst[1]['n']})."))


def pct(x):
    return f"{x*100:.0f}%"


def pf_fmt(x):
    return "&#8734;" if x == float("inf") else f"{x:.2f}"


def news_strip():
    if ff is None:
        return ""
    data = ff.read_feed_raw()
    if not data or "symbols" not in data or not data["symbols"]:
        return ("<h2>Live news bias</h2><div class='muted' style='font-size:12.5px'>"
                "No live data yet - run <b>Refresh live fundamentals</b> or schedule the "
                "5-min refresh. Full page: <a href='news_bias.html' style='color:#e6b312'>news_bias.html</a></div>")
    col = {"BUY": "#1f9d55", "SELL": "#e0526a", "NEUTRAL": "#3a4252"}
    chips = ""
    for sym, f in data["symbols"].items():
        sig = f.get("signal", "NEUTRAL")
        chips += (f"<div class='chip'><div class='cl'>{html.escape(f.get('label', sym))}</div>"
                  f"<div class='cb' style='background:{col.get(sig, '#3a4252')}'>{sig}</div>"
                  f"<div class='cn'>net {f.get('net_score', 0):+d} &middot; {f.get('n_total', 0)} hl</div></div>")
    gen = html.escape(str(data.get("generated", "")))
    return (f"<h2>Live news bias <a href='news_bias.html' style='font-size:12px;color:#e6b312'>full page &rarr;</a></h2>"
            f"<div class='chips'>{chips}</div>"
            f"<div class='muted' style='font-size:11px;margin-top:4px'>auto-scored news sentiment &middot; generated {gen}</div>")


def equity_svg(rs, w=900, h=200):
    if not rs:
        return "<p class='muted'>No closed trades yet.</p>"
    eq, c = [], 0.0
    for x in rs:
        c += x
        eq.append(c)
    lo, hi = min(eq + [0]), max(eq + [0])
    span = (hi - lo) or 1
    pad = 8
    pts = []
    for i, v in enumerate(eq):
        x = pad + i * (w - 2 * pad) / max(len(eq) - 1, 1)
        y = h - pad - (v - lo) * (h - 2 * pad) / span
        pts.append(f"{x:.1f},{y:.1f}")
    zy = h - pad - (0 - lo) * (h - 2 * pad) / span
    col = "#38c172" if eq[-1] >= 0 else "#e0526a"
    return (f"<svg viewBox='0 0 {w} {h}' style='width:100%;background:#0f131b;border-radius:10px'>"
            f"<line x1='0' y1='{zy:.1f}' x2='{w}' y2='{zy:.1f}' stroke='#2a3242' stroke-dasharray='4 4'/>"
            f"<polyline fill='none' stroke='{col}' stroke-width='2' points='{' '.join(pts)}'/></svg>")


def tbl(head, groups, order=None):
    keys = order or sorted(groups.keys())
    body = ""
    for k in keys:
        if k not in groups:
            continue
        b = block(groups[k])
        if not b:
            continue
        cls = "pos" if b["net"] >= 0 else "neg"
        body += (f"<tr><td>{html.escape(str(k))}</td><td>{b['n']}</td><td>{pct(b['wr'])}</td>"
                 f"<td>{pf_fmt(b['pf'])}</td><td class='{cls}'>{b['net']:+.1f}R</td>"
                 f"<td>{b['exp']:+.2f}R</td></tr>")
    return (f"<table><tr><th>{head}</th><th>Trades</th><th>Win</th><th>PF</th>"
            f"<th>Net</th><th>Exp</th></tr>{body}</table>")


icon = {"ok": "&#9989;", "warn": "&#9888;", "neutral": "&middot;"}
bord = {"ok": "#1f6b3f", "warn": "#7a5a12", "neutral": "#2a3550"}
hcards = ""
for kind, title, msg in health:
    hcards += (f"<div class='hc' style='border-color:{bord[kind]}'>"
               f"<div class='ht'>{icon[kind]} {title}</div><div class='hm'>{msg}</div></div>")

tiles = ""
if overall.get("n"):
    for label, val in [("Trades", overall["n"]), ("Win rate", pct(overall["wr"])),
                       ("Profit factor", pf_fmt(overall["pf"])),
                       ("Expectancy", f"{overall['exp']:+.2f}R"),
                       ("Net", f"{overall['net']:+.1f}R"),
                       ("Max DD", f"{overall['dd']:+.1f}R"),
                       ("Max losing streak", overall["maxloss"])]:
        tiles += f"<div class='tile'><div class='k'>{label}</div><div class='v'>{val}</div></div>"

note = ""
np = ROOT / "wti_note.txt"
if np.exists():
    try:
        note = html.escape(np.read_text()[:2600])
    except Exception:  # noqa: BLE001
        note = ""

links = [
    ("Live News & Bias", "news_bias.html", "BUY/SELL per pair from news, updates 5-min"),
    ("Performance dashboard", "dashboard.html", "Full stats + monthly returns"),
    ("Self-review", "self_review.html", "What predicts wins, in detail"),
    ("WTI smart-money chart", "wti_chart.html", "OTE, FVGs, order blocks, liquidity"),
    ("Signals app (PWA)", "xauusd-signals-app/index.html", "Phone-installable feed"),
    ("Landing page", "xauusd-signals-landing/index.html", "Public sales page"),
]
linkcards = "".join(
    f"<a class='lc' href='{href}'><div class='lt'>{t}</div><div class='ld'>{d}</div></a>"
    for t, href, d in links if (ROOT / href.split('/')[0]).exists())

doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Command Center</title><style>
body{{font-family:-apple-system,"Segoe UI",system-ui,sans-serif;background:#0b0e14;color:#e7eaf0;max-width:1000px;margin:18px auto;padding:0 16px}}
h1{{color:#e6b312;margin:0}} .sub{{color:#8b93a3;font-size:13px;margin:2px 0 16px}}
h2{{color:#e6b312;font-size:16px;margin:24px 0 8px}}
.grid{{display:grid;gap:10px}} .g7{{grid-template-columns:repeat(auto-fit,minmax(120px,1fr))}}
.g2{{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}}
.chips{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.chip{{background:#141a24;border:1px solid #232c3a;border-radius:12px;padding:10px 12px}}
.chip .cl{{font-weight:700;font-size:13px}} .chip .cb{{display:inline-block;color:#fff;font-weight:800;font-size:12px;padding:2px 10px;border-radius:6px;margin:5px 0}}
.chip .cn{{color:#8b93a3;font-size:11px}}
.tile{{background:#141a24;border:1px solid #232c3a;border-radius:12px;padding:12px}}
.tile .k{{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:#8b93a3}}
.tile .v{{font-size:22px;font-weight:800;margin-top:3px}}
.hc{{background:#141a24;border:1px solid #2a3550;border-radius:12px;padding:12px 14px}}
.ht{{font-weight:700;font-size:14px}} .hm{{color:#c3c9d4;font-size:12.5px;margin-top:4px;line-height:1.45}}
table{{width:100%;border-collapse:collapse;background:#141a24;border:1px solid #232c3a;border-radius:10px;overflow:hidden;margin:6px 0}}
th,td{{padding:8px 10px;text-align:left;font-size:12.5px;border-bottom:1px solid #202836}}
th{{background:#0f131b;color:#8b93a3;font-size:10.5px;text-transform:uppercase}}
.pos{{color:#38c172;font-weight:700}} .neg{{color:#e0526a;font-weight:700}} .muted{{color:#8b93a3;font-size:12px}}
.lc{{display:block;background:#141a24;border:1px solid #232c3a;border-radius:12px;padding:12px 14px;text-decoration:none;color:#e7eaf0}}
.lc:hover{{border-color:#e6b312}} .lt{{font-weight:700;font-size:13.5px;color:#e6b312}} .ld{{color:#8b93a3;font-size:12px;margin-top:2px}}
pre{{background:#0f131b;border:1px solid #232c3a;border-radius:10px;padding:12px;font-size:11.5px;white-space:pre-wrap;color:#c9cfda;max-height:340px;overflow:auto}}
.disc{{background:#1a1608;border:1px solid #3a3113;border-radius:10px;padding:11px 14px;font-size:11.5px;color:#d8c58c;margin-top:22px}}
</style></head><body>
<h1>&#9889; Signals Command Center</h1>
<div class="sub">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} &middot; {overall.get('n',0)} settled trades &middot; one screen for the whole platform</div>
{news_strip()}
<h2>Engine health</h2>
<div class="grid g2">{hcards or "<div class='hc'>No trades yet.</div>"}</div>
<h2>Headline performance</h2>
<div class="grid g7">{tiles or "<div class='tile'><div class='v'>No closed trades yet</div></div>"}</div>
<h2>Equity curve (R)</h2>{equity_svg(allr)}
<h2>What actually predicts wins</h2>
<div class="grid g2">
<div>{tbl("Confidence", by_conf, ["90-95","80-89","70-79","<70"])}</div>
<div>{tbl("Session", by_sess, ["London","New York","Asian"])}</div>
<div>{tbl("Market", by_sym)}</div>
<div>{tbl("Month", by_month)}</div>
</div>
<h2>Latest signal note</h2>{f"<pre>{note}</pre>" if note else "<p class='muted'>Run G_WTI_NOTE.bat to generate the latest note.</p>"}
<h2>Open every tool</h2>
<div class="grid g2">{linkcards}</div>
<div class="disc">&#9888; Live-tracked on the engine's data feed (gold uses a futures proxy). Sample still young - evidence building, not proof. Research/education only, not financial advice.</div>
</body></html>"""

(ROOT / "command_center.html").write_text(doc, encoding="utf-8")
print("wrote command_center.html |", overall.get("n", 0), "trades | news strip:", "yes" if ff else "no")
