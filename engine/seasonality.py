"""Seasonality — calendar-driven structural priors, per symbol.

Honesty note up front: none of this is computed from a statistical backtest
of decades of daily price data (we don't have that dataset loaded locally).
It encodes well-documented STRUCTURAL patterns tied to the calendar - real
recurring supply/demand cycles, not price geometry:

WTI (unchanged from the original single-symbol version):
  * driving season (Apr-Sep, peak Jun-Aug): US gasoline demand rises
  * refinery maintenance ("turnaround") windows (Feb-Mar, Sep-Oct): crude
    demand from refiners dips as plants go offline for maintenance
  * Atlantic hurricane season (Jun-Nov): Gulf of Mexico supply-disruption
    risk skews the distribution of outcomes, not the point forecast
  * winter heating demand (Nov-Feb): distillate demand rises

Gold (added 2026-07-28) - built on documented PHYSICAL gold-demand cycles,
mainly Indian and Chinese festival/cultural buying (the two largest
consumer gold markets), which is a genuinely different mechanism from
WTI's industrial/refinery calendar:
  * Chinese New Year (Jan-Feb, date varies): a major physical gold-buying
    occasion in China, the #2 consumer market
  * Akshaya Tritiya (Apr-May, India): a Hindu festival considered
    auspicious for gold purchases - a real, documented seasonal demand spike
  * summer lull (Jun-Aug): historically the quietest physical-demand window
    between spring festival buying and the autumn wedding/festival season
  * Indian wedding season + Navratri/Dussehra (Sep-Oct) and Diwali
    (Oct-Nov): India's biggest physical gold-demand window of the year -
    the World Gold Council's own reporting consistently flags Q4 as India's
    heaviest quarter for gold demand
  * December: demand tail from the Oct-Nov festival/wedding peak, plus
    Western year-end positioning

Bitcoin: deliberately NOT given a monthly table. There is no credible,
well-documented structural (non-price-pattern) seasonal demand cycle for
Bitcoin the way there is for a physical commodity - inventing one just to
have a number would be fabricating a signal, which this project's operating
rules explicitly rule out. bias()/alignment()/note() all return a neutral,
clearly-labeled "no seasonal edge" read for BTCUSD rather than a fabricated
lean.

Each month gets a qualitative bias and the reasoning behind it, used as a
SOFT confirmation only - weighted lightly in the confluence engine and never
a hard gate. Treat this as a structural prior a human trader would hold in
mind, not a statistically-validated edge.
"""
from __future__ import annotations

MONTHLY = {
    "WTIUSD": {
        1:  ("bull", "winter heating demand still elevated; early-year positioning"),
        2:  ("bear", "spring refinery maintenance begins; crude demand from refiners dips"),
        3:  ("bear", "peak refinery turnaround season; typically the weakest crude-demand month"),
        4:  ("bull", "driving season ramp-up begins; refiners returning from maintenance"),
        5:  ("bull", "driving season building; hurricane-season positioning starts"),
        6:  ("bull", "peak driving season starts; Atlantic hurricane season begins (Gulf supply risk)"),
        7:  ("bull", "peak driving season; hurricane season live"),
        8:  ("bull", "driving season tail; peak hurricane season (historically most active)"),
        9:  ("neutral", "driving season winding down; fall refinery maintenance begins; hurricane risk continues"),
        10: ("bear", "fall refinery turnaround season; hurricane season tapering"),
        11: ("bull", "winter heating demand build begins; OPEC+ meeting month (added volatility)"),
        12: ("bull", "peak winter heating demand; year-end positioning/liquidity thin"),
    },
    "XAUUSD": {
        1:  ("bull", "Chinese New Year physical demand building (China, #2 consumer market)"),
        2:  ("bull", "Chinese New Year gold-buying window (date varies year to year)"),
        3:  ("neutral", "post-Lunar New Year lull; no major festival demand driver"),
        4:  ("bull", "Akshaya Tritiya approaching (India) - auspicious gold-buying occasion"),
        5:  ("bull", "Akshaya Tritiya physical demand peak (India)"),
        6:  ("neutral", "summer lull - quietest physical-demand window of the year"),
        7:  ("neutral", "summer lull continues"),
        8:  ("neutral", "summer lull tail; early positioning for autumn festival season"),
        9:  ("bull", "Indian wedding season + Navratri begin - physical demand building"),
        10: ("bull", "Dussehra/Navratri and Diwali run-up (India) - major physical demand window"),
        11: ("bull", "Diwali physical demand peak (India's heaviest gold-demand quarter, per WGC reporting)"),
        12: ("neutral", "post-Diwali/wedding-season demand tail; Western year-end positioning"),
    },
    # BTCUSD deliberately omitted - see module docstring. bias()/alignment()
    # fall through to the neutral default for any symbol not in this dict.
}


def bias(month: int = None, symbol: str = "WTIUSD"):
    """`month` stays the first positional argument for backward compatibility
    with existing callers (e.g. `bias(3)`); `symbol` is new and keyword- or
    second-positional."""
    from datetime import date
    month = month or date.today().month
    table = MONTHLY.get(symbol)
    if table is None:
        return {"month": month, "lean": "neutral",
                "reason": f"no documented structural seasonal pattern for {symbol} - "
                          "reporting neutral rather than inventing one"}
    lean, reason = table.get(month, ("neutral", "no strong seasonal signature"))
    return {"month": month, "lean": lean, "reason": reason}


def alignment(direction: str, symbol: str = "WTIUSD", month: int = None):
    """Soft signal only. Returns {supports: True/False/None, note}."""
    b = bias(month, symbol)
    if b["lean"] == "neutral":
        return {"supports": None, "note": f"seasonality: {b['reason']} (neutral)"}
    bullish = b["lean"] == "bull"
    supports = bullish if direction == "long" else not bullish
    return {"supports": supports,
            "note": f"seasonality ({b['lean']}): {b['reason']}"}


def note(symbol: str = "WTIUSD", month: int = None):
    b = bias(month, symbol)
    return f"Seasonality ({b['lean']}): {b['reason']} — structural prior, not a backtested statistic"


if __name__ == "__main__":
    for sym in ("WTIUSD", "XAUUSD", "BTCUSD"):
        print(note(sym))
