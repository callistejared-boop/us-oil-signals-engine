"""Render an interactive ICT/SMC chart for WTI crude to wti_chart.html.

Draws candlesticks plus: dealing range, OTE (premium entry) zone,
equilibrium, all unfilled Fair Value Gaps, order blocks, buy/sell-side
liquidity, and the last BOS/CHoCH. Self-contained HTML (Plotly via CDN).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go                               # noqa: E402
from engine import config, markets                             # noqa: E402
from engine import structure as st                             # noqa: E402
from engine.data_loader import resample                        # noqa: E402

SYMBOL = "WTIUSD"
NBARS = 240

s = config.load()
df = markets.fetch(SYMBOL, s)
h1 = resample(df, "1h")
view = df.tail(NBARS)
price = float(df["Close"].iloc[-1])
x0, x1 = view.index[0], view.index[-1]

rng_hi, rng_lo = st.dealing_range(h1, lookback=200)
eq = (rng_hi + rng_lo) / 2
ote_lo = rng_lo + 0.62 * (rng_hi - rng_lo)
ote_hi = rng_lo + 0.79 * (rng_hi - rng_lo)

fig = go.Figure(go.Candlestick(
    x=view.index, open=view["Open"], high=view["High"],
    low=view["Low"], close=view["Close"], name="WTI",
    increasing_line_color="#26a69a", decreasing_line_color="#ef5350"))


def box(y0, y1, color, text, xa=None):
    fig.add_shape(type="rect", xref="x", yref="y", x0=(xa or x0), x1=x1,
                  y0=y0, y1=y1, fillcolor=color, opacity=0.18,
                  line=dict(width=0), layer="below")
    fig.add_annotation(x=x1, y=(y0 + y1) / 2, text=text, showarrow=False,
                       xanchor="left", font=dict(size=10, color="#cfd3da"))


def line(y, color, text, dash="dot"):
    fig.add_hline(y=y, line=dict(color=color, width=1, dash=dash))
    fig.add_annotation(x=x1, y=y, text=text, showarrow=False, xanchor="left",
                       font=dict(size=10, color=color))


# dealing range + OTE + equilibrium
box(rng_lo, rng_hi, "#5b6472", "dealing range")
box(ote_lo, ote_hi, "#e6b312", "OTE / premium entry")
line(eq, "#9aa0ab", f"equilibrium {eq:.2f}", "dash")
line(rng_hi, "#ef5350", f"range high {rng_hi:.2f}", "solid")
line(rng_lo, "#26a69a", f"range low {rng_lo:.2f}", "solid")

# unfilled Fair Value Gaps (draw boxes from creation to now)
tail = df.tail(NBARS)
for g in st.find_fvgs(tail):
    if g.filled_idx is None:
        c = "#26a69a" if g.kind == "bull" else "#ef5350"
        box(g.bottom, g.top, c, f"{g.kind} FVG", xa=tail.index[g.created_idx])

# last two order blocks (opposite candle before displacement)
d = tail.reset_index()
atr = (tail["High"] - tail["Low"]).tail(20).mean()
obs = 0
for i in range(len(d) - 2, 2, -1):
    o, c, hi, lo = d["Open"][i], d["Close"][i], d["High"][i], d["Low"][i]
    if c > o and (c - o) > 1.2 * atr and d["Close"][i - 1] < d["Open"][i - 1]:
        box(d["Low"][i - 1], d["High"][i - 1], "#4a90e2", "bull OB",
            xa=tail.index[i - 1]); obs += 1
    elif c < o and (o - c) > 1.2 * atr and d["Close"][i - 1] > d["Open"][i - 1]:
        box(d["Low"][i - 1], d["High"][i - 1], "#b061d6", "bear OB",
            xa=tail.index[i - 1]); obs += 1
    if obs >= 2:
        break

# liquidity: recent swing highs (BSL) / lows (SSL)
sw = st.find_swings(tail["High"].values, tail["Low"].values, k=2)
for hgh in sorted({round(float(x.price), 2) for x in sw if x.kind == "H"})[-2:]:
    line(hgh, "#ff8a80", f"BSL {hgh}", "dot")
for lw in sorted({round(float(x.price), 2) for x in sw if x.kind == "L"})[:2]:
    line(lw, "#80cbc4", f"SSL {lw}", "dot")

# structure events (BOS/CHoCH)
ss = st.structure_series(tail)
for ts, row in ss[ss["event"] != ""].tail(4).iterrows():
    up = "up" in row["event"]
    fig.add_annotation(x=ts, y=float(tail.loc[ts, "Low" if up else "High"]),
                       text=row["event"].replace("_", " "), showarrow=True,
                       arrowhead=2, ay=(30 if up else -30),
                       font=dict(size=9, color="#e6b312"))

line(price, "#ffffff", f"price {price:.2f}", "dash")

fig.update_layout(
    title=f"WTI CRUDE — ICT / SMC map · price {price:.2f} · "
          f"range {rng_lo:.2f}-{rng_hi:.2f}",
    template="plotly_dark", xaxis_rangeslider_visible=False, height=760,
    margin=dict(l=40, r=140, t=50, b=40))
out = ROOT / "wti_chart.html"
fig.write_html(str(out), include_plotlyjs="cdn")
print("wrote", out)
