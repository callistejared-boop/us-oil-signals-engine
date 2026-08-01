"""Self-improvement engine (transparent, not a black box).

Reads the live trade journal and reports which conditions actually predict
wins - by confidence, session, market, direction, weekday, and NEWS AGREEMENT
(whether the live news bias agreed with the trade at entry) - then prints
plain-English recommendations. It does NOT silently change the engine; it tells
YOU what the data says so weighting changes are deliberate and auditable.
Writes self_review.html and prints the key findings.
"""
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


def seg(rs):
    n = len(rs)
    if not n:
        return None
    w = [x for x in rs if x > 1e-9]
    l = [x for x in rs if x < -1e-9]
    gw, gl = sum(w), abs(sum(l))
    return {"n": n, "wr": len(w) / n, "net": sum(rs), "exp": sum(rs) / n,
            "pf": (gw / gl) if gl else float("inf")}


def session_of(iso):
    try:
        h = datetime.fromisoformat(iso).hour
    except Exception:  # noqa: BLE001
        return "unknown"
    return ("London" if 7 <= h < 12 else "New York" if 12 <= h < 21 else "Asian")


def weekday_of(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%a")
    except Exception:  # noqa: BLE001
        return "?"


def conf_bucket(c):
    c = int(c or 0)
    return "90-95" if c >= 90 else "80-89" if c >= 80 else "70-79" if c >= 70 else "<70"


def news_bucket(r):
    d = r.get("news_delta", 0) or 0
    return "agree" if d > 0 else "conflict" if d < 0 else "none"


def regime_bucket(r):
    return r.get("regime_trend") or "none"


def guard_bucket(r):
    return r.get("guard_action") or "none"


def confluence_bucket(r):
    sc = r.get("confluence_score", -1)
    if sc is None or sc < 0:
        return "n/a (pre-MAST)"
    return "80-100" if sc >= 80 else "70-79" if sc >= 70 else "<70"


def combo_bucket(r):
    return f"{regime_bucket(r)} / {guard_bucket(r)}"


dims = {
    "Confidence": lambda r: conf_bucket(r.get("confidence")),
    "Confluence score (MAST)": confluence_bucket,
    "Session (UTC)": lambda r: session_of(r.get("opened", "")),
    "Market": lambda r: r.get("symbol", "?"),
    "Direction": lambda r: r.get("direction", "?"),
    "Weekday": lambda r: weekday_of(r.get("opened", "")),
    "News agreement": news_bucket,
    "Regime": regime_bucket,
    "Range guard": guard_bucket,
    "Strategy combination": combo_bucket,
}


def max_drawdown_r(rs_in_order):
    peak = cum = dd = 0.0
    for x in rs_in_order:
        cum += x
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return round(dd, 2)

results = {}
for _name, _fn in dims.items():
    _g = defaultdict(list)
    for _r in closed:
        _g[_fn(_r)].append(_r["result_r"])
    results[_name] = {k: seg(v) for k, v in _g.items() if seg(v)}

recs = []
cb = results.get("Confidence", {})
order = [b for b in ["90-95", "80-89", "70-79", "<70"] if b in cb]
if len(order) >= 2:
    hi, lo = cb[order[0]]["wr"], cb[order[-1]]["wr"]
    if hi > lo + 0.05:
        recs.append("Confidence IS predictive: top bucket wins more than the low bucket. Trust the score more when sizing.")
    elif lo > hi + 0.05:
        recs.append("Confidence looks INVERTED (low bucket outperforms) - small sample; monitor weekly, do NOT rewire yet.")
    else:
        recs.append("Confidence buckets perform similarly - score not separating winners yet; keep collecting.")

# --- the key learning question: does news agreement predict wins? ----------
na = results.get("News agreement", {})
a, c, none = na.get("agree"), na.get("conflict"), na.get("none")
if a and c and a["n"] >= 5 and c["n"] >= 5:
    if a["exp"] - c["exp"] > 0.2:
        recs.append(f"NEWS IS EARNING ITS WEIGHT: agree {a['exp']:+.2f}R (win {a['wr']*100:.0f}%) "
                    f"vs conflict {c['exp']:+.2f}R ({c['wr']*100:.0f}%). Consider widening the news bound.")
    elif c["exp"] - a["exp"] > 0.2:
        recs.append(f"NEWS MAY BE HURTING: conflict {c['exp']:+.2f}R vs agree {a['exp']:+.2f}R - the "
                    "opposite of intended. Consider shrinking the news bound if it persists.")
    else:
        recs.append(f"News agreement roughly neutral (agree {a['exp']:+.2f}R vs conflict {c['exp']:+.2f}R).")
elif a and none and a["n"] >= 6 and none["exp"] - a["exp"] > 0.4:
    recs.append(f"WATCH - news-AGREEING trades are UNDERPERFORMING: agree {a['exp']:+.2f}R "
                f"(win {a['wr']*100:.0f}%, n={a['n']}) vs no-news {none['exp']:+.2f}R "
                f"(win {none['wr']*100:.0f}%). Early sign the news nudge isn't paying; if it holds past "
                "~15 agree trades, shrink the news bound (CONTEXT_CAP / news weight). Not enough to rewire yet.")
else:
    recs.append("News-agreement learning loop is active but needs more news-stamped trades "
                "before it can judge whether news helps.")

for dim in ("Session (UTC)", "Market", "Direction"):
    d = {k: v for k, v in results.get(dim, {}).items() if k != "?"}
    if len(d) >= 2:
        best = max(d.items(), key=lambda kv: kv[1]["exp"])
        worst = min(d.items(), key=lambda kv: kv[1]["exp"])
        if best[1]["exp"] - worst[1]["exp"] > 0.3 and worst[1]["n"] >= 5:
            recs.append(dim + ": strongest '" + str(best[0]) + "', weakest '" + str(worst[0]) + f"' (n={worst[1]['n']}). Consider down-weighting the laggard.")

# --- does the RANGE GUARD earn its keep? validate before trusting ----------
rgd_res = results.get("Range guard", {})
flagged = [v for k, v in rgd_res.items() if k in ("downgrade", "suppress")]
allowed = rgd_res.get("allow")
fn = sum(v["n"] for v in flagged)
if flagged and allowed and fn >= 5 and allowed["n"] >= 5:
    fexp = sum(v["exp"] * v["n"] for v in flagged) / fn
    fwr = sum(v["wr"] * v["n"] for v in flagged) / fn
    if allowed["exp"] - fexp > 0.15:
        recs.append(f"RANGE GUARD IS VALIDATED: guard-flagged trades {fexp:+.2f}R (win {fwr*100:.0f}%, "
                    f"n={fn}) vs clean trades {allowed['exp']:+.2f}R (win {allowed['wr']*100:.0f}%). "
                    "The chase filter is separating losers — safe to raise its weight / enable SUPPRESS_MODE.")
    elif fexp - allowed["exp"] > 0.15:
        recs.append(f"RANGE GUARD LOOKS TOO HARSH: flagged trades {fexp:+.2f}R actually BEAT clean "
                    f"{allowed['exp']:+.2f}R (n={fn}). Loosen thresholds or reduce the penalty.")
    else:
        recs.append(f"Range guard roughly neutral so far (flagged {fexp:+.2f}R vs clean "
                    f"{allowed['exp']:+.2f}R, n={fn}). Keep downgrading, not suppressing, until a gap appears.")
else:
    recs.append("Range guard is live and stamping trades, but needs more guard-flagged closed trades "
                "before it can prove whether the chase filter actually predicts losers. Downgrade-only "
                "until then (SUPPRESS_MODE stays off).")


# --- performance analytics summary (rule-based aggregation, not ML) --------
ordered_rs = [r["result_r"] for r in sorted(closed, key=lambda r: str(r.get("opened", "")))]
max_dd = max_drawdown_r(ordered_rs)

sess_d = {k: v for k, v in results.get("Session (UTC)", {}).items()}
best_session = max(sess_d.items(), key=lambda kv: kv[1]["exp"])[0] if sess_d else "n/a"
worst_session = min(sess_d.items(), key=lambda kv: kv[1]["exp"])[0] if sess_d else "n/a"

combo_d = {k: v for k, v in results.get("Strategy combination", {}).items() if v["n"] >= 3}
best_combo = max(combo_d.items(), key=lambda kv: kv[1]["exp"])[0] if combo_d else "n/a (need >=3 trades per combo)"

market_d = {k: v for k, v in results.get("Market", {}).items()}
best_market = max(market_d.items(), key=lambda kv: kv[1]["wr"])[0] if market_d else "n/a"

analytics_lines = [
    f"Max drawdown: {max_dd:.1f}R",
    f"Best session: {best_session} | Worst session: {worst_session}",
    f"Best strategy combination (regime/guard, n>=3): {best_combo}",
    f"Highest win-rate market: {best_market}",
    "Most reliable timeframe: not yet trackable — every signal already fuses "
    "D/4H/1H/15m, so no single timeframe is isolated per trade. Would need "
    "per-timeframe trade tagging to measure honestly (not fabricated here).",
    "Highest-accuracy pattern: not yet trackable — price-action patterns "
    "(pin bar/engulfing/etc.) aren't stamped on the journal yet. Add "
    "price_action stamping to enable this in a future pass.",
]


def tbl(name, d, order=None):
    keys = order or sorted(d.keys())
    body = ""
    for k in keys:
        if k not in d:
            continue
        b = d[k]
        pf = "inf" if b["pf"] == float("inf") else f"{b['pf']:.2f}"
        cls = "pos" if b["net"] >= 0 else "neg"
        body += ("<tr><td>" + str(k) + f"</td><td>{b['n']}</td><td>{b['wr']*100:.0f}%</td><td>{pf}</td>"
                 + f"<td class='{cls}'>{b['net']:+.1f}R</td><td>{b['exp']:+.2f}R</td></tr>")
    return ("<h2>" + name + "</h2><table><tr><th>" + name.split()[0]
            + "</th><th>Trades</th><th>Win</th><th>PF</th><th>Net</th><th>Exp</th></tr>" + body + "</table>")


overall = seg([r["result_r"] for r in closed]) or {"n": 0, "wr": 0, "net": 0, "pf": 0}
reclist = "".join("<li>" + r + "</li>" for r in recs)
S = "<style>body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:#0b0e14;color:#e7eaf0;max-width:920px;margin:20px auto;padding:0 16px}h1,h2{color:#e6b312}h2{font-size:17px;margin:22px 0 6px}table{width:100%;border-collapse:collapse;background:#141a24;border:1px solid #232c3a;border-radius:10px;overflow:hidden;margin-bottom:6px}th,td{padding:8px 10px;text-align:left;font-size:13px;border-bottom:1px solid #202836}th{background:#0f131b;color:#8b93a3;font-size:11px;text-transform:uppercase}.pos{color:#38c172;font-weight:700}.neg{color:#e0526a;font-weight:700}.rec{background:#141a24;border:1px solid #2a3550;border-radius:10px;padding:12px 16px}.muted{color:#8b93a3;font-size:13px}</style>"
doc = ("<!DOCTYPE html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
       + S + "<h1>Signal Self-Review</h1><p class='muted'>Generated " + datetime.now().strftime('%Y-%m-%d %H:%M')
       + f" - {overall['n']} trades - win {overall['wr']*100:.0f}% - net {overall['net']:+.1f}R - PF {overall['pf']:.2f}</p>"
       + "<h2>Recommendations</h2><div class='rec'><ul>" + reclist + "</ul></div>"
       + "<h2>Performance analytics</h2><div class='rec'><ul>"
       + "".join("<li>" + x + "</li>" for x in analytics_lines) + "</ul></div>"
       + tbl("Confluence score (MAST)", results.get("Confluence score (MAST)", {}),
            ["80-100", "70-79", "<70", "n/a (pre-MAST)"])
       + tbl("Strategy combination", results.get("Strategy combination", {}))
       + tbl("News agreement", results.get("News agreement", {}), ["agree", "conflict", "none"])
       + tbl("Regime", results.get("Regime", {}), ["trend", "range", "none"])
       + tbl("Range guard", results.get("Range guard", {}), ["allow", "downgrade", "suppress", "none"])
       + tbl("Confidence bucket", results.get("Confidence", {}), ["90-95", "80-89", "70-79", "<70"])
       + tbl("Session (UTC)", results.get("Session (UTC)", {}), ["London", "New York", "Asian"])
       + tbl("Market", results.get("Market", {}))
       + tbl("Direction", results.get("Direction", {}))
       + tbl("Weekday", results.get("Weekday", {}), ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
       + "<p class='muted'>News agreement = did the live news bias agree with the trade direction at entry "
       "(+delta), conflict (-delta), or was there no fresh news (none). Transparent by design: reports what "
       "the data says; weighting stays a human decision. Young sample - a compass, not gospel.</p>")
(ROOT / "self_review.html").write_text(doc, encoding="utf-8")

print(f"=== SELF-REVIEW ({overall['n']} trades, win {overall['wr']*100:.0f}%, net {overall['net']:+.1f}R) ===")
for name in dims:
    print("\n[" + name + "]")
    for k, b in sorted(results[name].items(), key=lambda kv: -kv[1]["exp"]):
        pf = "inf" if b["pf"] == float("inf") else f"{b['pf']:.2f}"
        print(f"  {str(k):12s} n={b['n']:2d} win={b['wr']*100:3.0f}% net={b['net']:+5.1f}R exp={b['exp']:+.2f}R pf={pf}")
print("\n=== RECOMMENDATIONS ===")
for r in recs:
    print(" -", r)
