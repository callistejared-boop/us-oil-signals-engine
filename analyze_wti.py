"""On-demand full analysis for WTI crude (CL=F). Writes wti_report.txt with
the ICT/SMC read, classical technicals, key reaction zones, and any setup.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import config, markets, ict, technicals, signals   # noqa: E402
from engine.data_loader import resample                        # noqa: E402

s = config.load()
out = []
try:
    df = markets.fetch("WTIUSD", s)
    r = ict.read(df)
    tech = technicals.compute(resample(df, "1h"))
    sig = signals.analyze(df.tail(12000), min_conf=signals.WATCH_THRESHOLD,
                          symbol="WTIUSD")
    lo, hi = r["range"]
    out.append("WTI CRUDE (CL=F) — FULL ANALYSIS")
    out.append(f"price: {r['price']:.2f}   bars: {len(df)}   last: {df.index[-1]}")
    out.append("")
    out.append("KEY ZONES (where price is likely to react):")
    out.append(f"  Resistance / range high : {hi:.2f}")
    out.append(f"  Equilibrium (50%)       : {(lo+hi)/2:.2f}")
    out.append(f"  OTE entry zone          : {r['ote'][0]:.2f} - {r['ote'][1]:.2f}")
    out.append(f"  Support / range low     : {lo:.2f}")
    if r.get("fvg"):
        out.append(f"  Unfilled FVG            : {r['fvg'][0]} - {r['fvg'][1]}")
    if r.get("ob"):
        out.append(f"  Order block             : {r['ob'][0]} - {r['ob'][1]}")
    out.append(f"  Buy-side liquidity (stops above): {r['liq']['buyside']}")
    out.append(f"  Sell-side liquidity (stops below): {r['liq']['sellside']}")
    out.append("")
    out.append("SMART MONEY READ (ICT / SMC):")
    out += ["  " + l for l in r["lines"]]
    out.append(f"  directional lean: {r['lean'].upper()} (est ~{r['prob']}%)")
    out.append("")
    out.append(f"TECHNICALS (1H) overall: {tech.bias.upper()}")
    out += ["  - " + l for l in tech.lines]
    out.append("")
    if sig:
        out.append(f"SETUP: {sig.tier.upper()} {sig.direction.upper()} | conf {sig.confidence} "
                   f"| entry {sig.entry} stop {sig.stop} target {sig.target} RR {sig.rr}")
    else:
        out.append("SETUP: none qualifying right now (engine standing aside)")
except Exception as exc:  # noqa: BLE001
    out.append(f"ERROR: {exc}")

(ROOT / "wti_report.txt").write_text("\n".join(out), encoding="utf-8")
print("done")
