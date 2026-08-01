"""Forward-test scoreboard — the numbers that decide whether to scale.

Tracks the CURRENT forward-test window (trades closed after the window start,
default = when paper mode began) toward the 30-trade validation target, and
reports the KPIs that actually matter: expectancy (avg R/trade), win rate,
profit factor, net R, and max drawdown in R. Prints a clear verdict rule:

    scale IF  expectancy > +0.15R  AND  max drawdown < 6R  after >=30 trades
    adjust IF expectancy in [-0.1, +0.15]R  -> review self_review.html dims
    stop/rebuild IF expectancy < -0.1R after >=30 trades

Writes forward_report.txt; --send posts it to your Telegram DM (never the
public channel — this is your private scoreboard).
"""
import json
import pathlib
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from engine import store  # noqa: E402

TARGET_N = 30
WINDOW_START = "2026-07-17"   # forward test begins today (paper mode on)
FOCUS_SYMBOL = "WTIUSD"       # the product is WTI-only; legacy multi-market
                              # trades from before the pivot must not dilute
                              # the number that decides whether to scale


def drawdown_r(rs):
    """Max peak-to-trough drawdown of the cumulative R curve."""
    peak = cum = 0.0
    dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return round(dd, 2)


def build(rows=None, window_start=WINDOW_START, target=TARGET_N,
         symbol=FOCUS_SYMBOL):
    rows = rows if rows is not None else store.load_array(ROOT / "trades.json")
    closed = sorted((r for r in rows
                     if r.get("status") in ("win", "loss", "scratch")
                     and str(r.get("closed", ""))[:10] >= window_start
                     and (symbol is None or r.get("symbol") == symbol)),
                    key=lambda r: str(r.get("closed", "")))
    rs = [float(r.get("result_r", 0) or 0) for r in closed]
    n = len(rs)
    wins = sum(1 for x in rs if x > 1e-9)
    gross_w = sum(x for x in rs if x > 1e-9)
    gross_l = abs(sum(x for x in rs if x < -1e-9))
    exp = (sum(rs) / n) if n else 0.0
    pf = (gross_w / gross_l) if gross_l else (float("inf") if gross_w else 0.0)
    dd = drawdown_r(rs)
    open_n = sum(1 for r in rows if r.get("status") == "open"
                and (symbol is None or r.get("symbol") == symbol))
    legacy_open = sum(1 for r in rows if r.get("status") == "open"
                      and symbol is not None and r.get("symbol") != symbol)

    if n >= target:
        if exp > 0.15 and dd < 6:
            verdict = ("VALIDATED: expectancy is positive with controlled drawdown. "
                       "Cleared to scale risk gradually (0.5% -> 1%).")
        elif exp >= -0.1:
            verdict = ("INCONCLUSIVE: roughly break-even. Do NOT scale. Review "
                       "self_review.html for which condition (session/regime/guard) "
                       "is dragging, cut that, run 30 more.")
        else:
            verdict = ("NOT WORKING as-is: negative expectancy over a full window. "
                       "Stop live risk; rebuild around the strongest segment only.")
    else:
        verdict = (f"IN PROGRESS: {n}/{target} closed trades. Keep paper mode on; "
                   "no real size until the window completes. Patience IS the edge.")

    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    L = [
        "==============================================",
        "  FORWARD TEST SCOREBOARD (private)" + (f" — {symbol}" if symbol else ""),
        f"  window since {window_start} | generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "==============================================",
        f"progress    : {n}/{target} closed  ({open_n} open now)",
        f"expectancy  : {exp:+.2f}R per trade   <- THE number",
        f"win rate    : {(wins/n*100 if n else 0):.0f}%  (win-rate is NOT the goal; R is)",
        f"profit factor: {pf_s}",
        f"net         : {sum(rs):+.1f}R",
        f"max drawdown: {dd:.1f}R",
        "",
        "VERDICT: " + verdict,
        "",
        "Rules: risk fixed 0.5-1% | day-stop -2R (auto-enforced) | 1 position max "
        "(auto-enforced) | no size-up mid-window.",
    ]
    if legacy_open:
        L.append(f"NOTE: {legacy_open} pre-pivot legacy trade(s) in other markets "
                 "are still open in the journal (stale, no live feed) — excluded "
                 "from this WTI-only scoreboard, not counted toward the target.")
    return "\n".join(L), {"n": n, "exp": round(exp, 3), "dd": dd,
                          "net": round(sum(rs), 2), "wins": wins}


def main():
    text, _ = build()
    (ROOT / "forward_report.txt").write_text(text, encoding="utf-8")
    print(text)
    if "--send" in sys.argv:
        try:
            import urllib.parse
            import urllib.request
            from engine import config
            s = config.load()
            data = urllib.parse.urlencode(
                {"chat_id": s.telegram_chat_id, "text": text}).encode()
            r = json.load(urllib.request.urlopen(
                "https://api.telegram.org/bot" + s.telegram_bot_token
                + "/sendMessage", data=data, timeout=25))
            print("[sent to DM]", r.get("ok"))
        except Exception as exc:  # noqa: BLE001
            print("send err:", exc)


if __name__ == "__main__":
    main()
