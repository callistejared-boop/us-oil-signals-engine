"""Top-down multi-timeframe ICT/SMC analysis (4H -> 1H -> 15m) for one symbol.

For each timeframe it computes: structure trend (bias), dealing range with
premium/discount + OTE, resting liquidity (buy/sell-side), the last BOS/CHoCH,
the nearest unfilled FVG, the most recent order block, and a concrete entry
PLAN (zone / stop / targets) with the ICT reasoning. Writes analysis_tf.txt.
Live data via the engine's fetch; NO Telegram send - this is analysis only.
"""
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import config, markets, ict, bias_adjust as ba, fundamentals_feed as ff  # noqa: E402
from engine import structure as st                                                    # noqa: E402
from engine.data_loader import resample                                               # noqa: E402


def tf_block(df, label, symbol):
    price = float(df["Close"].iloc[-1])
    trend = ict.tf_trend(df)
    direction = "long" if trend == "bull" else "short" if trend == "bear" else None
    rng_hi, rng_lo = st.dealing_range(df, lookback=200)
    span = rng_hi - rng_lo
    pos = st.range_position(price, rng_hi, rng_lo)
    eq = (rng_hi + rng_lo) / 2
    ote_lo, ote_hi = rng_lo + 0.62 * span, rng_lo + 0.79 * span   # discount OTE (for longs)
    ote_hi_s, ote_lo_s = rng_hi - 0.62 * span, rng_hi - 0.79 * span  # premium OTE (for shorts)
    zone = ("discount" if pos <= 0.4 else "premium" if pos >= 0.6 else "equilibrium")
    if pos > 1:
        zone = "above range (breakout)"
    elif pos < 0:
        zone = "below range (breakdown)"
    liq = ict.liquidity(df, price)
    kind = "bull" if direction == "long" else "bear" if direction == "short" else None
    fvg = ict.nearest_fvg(df, kind, price) if kind else None
    ob = ict.order_block(df, direction) if direction else None
    ev = ict.last_event(df)

    L = [f"=== {label} ===",
         f"Bias/structure: {trend.upper()}   price {price:.2f}",
         f"Dealing range {rng_lo:.2f}-{rng_hi:.2f} | eq {eq:.2f} | price is in {zone.upper()} (pos {pos:.2f})",
         f"Buy-side liquidity (targets up): {liq['buyside'] or '-'}",
         f"Sell-side liquidity (targets down): {liq['sellside'] or '-'}",
         f"Last structure event: {ev}",
         f"Nearest unfilled FVG: {(str(fvg[0])+'-'+str(fvg[1])) if fvg else '-'}",
         f"Order block: {(str(ob[0])+'-'+str(ob[1])) if ob else '-'}"]

    # ---- entry plan ----
    plan = []
    if direction == "long":
        buy_lo, buy_hi = (fvg if fvg else (ote_lo, ote_hi))
        src = "bull FVG" if fvg else "discount OTE (0.62-0.79)"
        stop = round((ob[0] if ob else rng_lo) - 0.15 * span * 0.1, 2)
        stop = round(min(stop, buy_lo - 0.05 * (buy_hi - buy_lo) - 0.01), 2)
        t1 = liq["buyside"][0] if liq["buyside"] else round(eq + 0.5 * (rng_hi - eq), 2)
        t2 = liq["buyside"][1] if len(liq["buyside"]) > 1 else round(rng_hi, 2)
        if zone in ("discount", "equilibrium") or pos <= 0.6:
            plan.append(f"ENTRY (long): buy the {src} at {buy_lo:.2f}-{buy_hi:.2f} on a bullish reaction.")
        else:
            plan.append(f"WAIT: price in premium - do NOT chase. Wait for pullback to the {src} "
                        f"at {buy_lo:.2f}-{buy_hi:.2f}, then buy the reaction.")
        plan.append(f"Stop: {stop:.2f} (below the {'order block' if ob else 'range low'}).")
        plan.append(f"Targets: TP1 {t1} (buy-side liquidity), TP2 {t2} (range high / next pool).")
    elif direction == "short":
        sell_lo, sell_hi = (fvg if fvg else (ote_lo_s, ote_hi_s))
        src = "bear FVG" if fvg else "premium OTE (0.62-0.79)"
        stop = round((ob[1] if ob else rng_hi) + 0.001 * rng_hi, 2)
        t1 = liq["sellside"][0] if liq["sellside"] else round(eq - 0.5 * (eq - rng_lo), 2)
        t2 = liq["sellside"][1] if len(liq["sellside"]) > 1 else round(rng_lo, 2)
        if zone in ("premium", "equilibrium") or pos >= 0.4:
            plan.append(f"ENTRY (short): sell the {src} at {sell_lo:.2f}-{sell_hi:.2f} on a bearish reaction.")
        else:
            plan.append(f"WAIT: price in discount - do NOT chase. Wait for rally to the {src} "
                        f"at {sell_lo:.2f}-{sell_hi:.2f}, then sell the reaction.")
        plan.append(f"Stop: {stop:.2f} (above the {'order block' if ob else 'range high'}).")
        plan.append(f"Targets: TP1 {t1} (sell-side liquidity), TP2 {t2} (range low / next pool).")
    else:
        plan.append("NO CLEAN ENTRY: structure is ranging - stand aside until a CHoCH picks a side.")
    L.append("PLAN: " + " ".join(plan))
    return "\n".join(L), direction


def main():
    sym = sys.argv[1] if len(sys.argv) > 1 else "WTIUSD"
    s = config.load()
    df15 = markets.fetch(sym, s)
    frames = [("4-HOUR (higher-timeframe bias & draw on liquidity)", resample(df15, "4h")),
              ("1-HOUR (intermediate structure & primary zone)", resample(df15, "1h")),
              ("15-MIN (execution / entry trigger)", df15)]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    price = float(df15["Close"].iloc[-1])
    feed = ff.load_feed(sym) or {}
    news = f"{feed.get('signal','n/a')} ({feed.get('strength','')})" if feed else "n/a"
    ctx_adj, ctx_delta, ctx_why = ba.apply_context(sym, "long", 75)
    out = [f"{sym} — TOP-DOWN ICT/SMC ANALYSIS", now, f"spot ~{price:.2f}",
           f"Live news bias: {news} | context nudge (news+killzone): {ctx_delta:+d}", ""]
    dirs = []
    for label, fr in frames:
        blk, d = tf_block(fr, label, sym)
        out.append(blk)
        out.append("")
        dirs.append(d)
    conf = dirs.count("long") - dirs.count("short")
    verdict = ("ALL THREE ALIGN LONG - highest-confidence long context." if dirs == ["long", "long", "long"]
               else "ALL THREE ALIGN SHORT - highest-confidence short context." if dirs == ["short", "short", "short"]
               else "TIMEFRAMES MIXED - trade the lower-TF entry only in the direction of the 4H bias; reduce size.")
    out.append("TOP-DOWN VERDICT: " + verdict)
    out.append("Research/education only - not financial advice.")
    (ROOT / "analysis_tf.txt").write_text("\n".join(out), encoding="utf-8")
    print("wrote analysis_tf.txt")
    print("\n".join(out)[:600])


if __name__ == "__main__":
    main()
