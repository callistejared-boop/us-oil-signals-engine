"""Live multi-pair news feed - key-free, transparent, fail-safe.

For each traded pair it pulls recent headlines from public news RSS (Google
News aggregates Reuters/Bloomberg/CNBC/FT/etc), scores each headline with a
pair-specific, NEGATION-AWARE sentiment lexicon, and derives a BUY / SELL /
NEUTRAL bias plus a signal STRENGTH and a plain-English "why". Writes
fundamentals.json (nested by symbol) which the trade notes, the live interface,
and the bias-flip alerter all read.

This is a HEADLINE-SENTIMENT HEURISTIC, labelled as such everywhere - a
transparent decision aid, not a human analyst, never presented as certainty.
"""
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
FEED_PATH = ROOT / "fundamentals.json"
import sys as _sys
_sys.path.insert(0, str(ROOT))

# Negators: if any appears just before a matched term, that term is cancelled
# (e.g. "Iran denies closing Hormuz", "no ceasefire", "rules out output cut").
NEGATORS = ("no ", "not ", "never ", "denies", "deny", "denied", "rules out",
            "rule out", "ruled out", "without", "avoid", "averts", "avert",
            "dismiss", "reject", "unlikely", "no sign", "fails to", "halts talks")


def _q(terms, window="3d"):
    from urllib.parse import quote_plus
    return (f"https://news.google.com/rss/search?q={quote_plus(terms)}+when:{window}"
            "&hl=en-US&gl=US&ceid=US:en")


SYMBOLS = {
    "WTIUSD": {
        "label": "US Oil",
        "queries": [_q("WTI crude oil price"), _q("Strait of Hormuz oil Iran"),
                    _q("OPEC oil output"), _q("EIA crude oil inventories", "5d")],
        "bull": {"strike": 3, "airstrike": 3, "attack": 3, "missile": 3, "drone": 2,
                 "closed": 3, "blockade": 4, "disrupt": 3, "disruption": 3, "sanction": 2,
                 "tension": 2, "escalat": 3, "conflict": 2, "war": 2, "outage": 3,
                 "halt": 2, "seize": 3, "threat": 2, "output cut": 3, "production cut": 3,
                 "supply cut": 3, "draw": 2, "drawdown": 2, "deficit": 2, "shortage": 3,
                 "tight": 2, "risk premium": 3, "surge": 2, "jump": 2, "spike": 2, "rally": 2},
        "bear": {"ceasefire": 4, "cease-fire": 4, "truce": 3, "de-escalat": 3, "deescalat": 3,
                 "reopen": 3, "eases": 2, "deal": 2, "agreement": 2, "build": 2, "builds": 2,
                 "glut": 3, "oversupply": 3, "surplus": 3, "output add": 3, "raise output": 3,
                 "boost output": 3, "increase output": 3, "hike output": 3, "weak demand": 3,
                 "demand cut": 2, "recession": 2, "slump": 2, "resume": 2, "restart": 2},
    },
    "XAUUSD": {
        "label": "Gold",
        "queries": [_q("gold price forecast"), _q("Federal Reserve interest rate cut"),
                    _q("US dollar inflation CPI"), _q("gold safe haven geopolitical")],
        "bull": {"rate cut": 4, "cuts rate": 4, "cut rates": 4, "dovish": 3, "weak dollar": 3,
                 "dollar falls": 3, "dollar slips": 2, "inflation": 2, "cpi rises": 3,
                 "safe haven": 3, "haven demand": 3, "geopolit": 2, "war": 2, "tension": 2,
                 "crisis": 2, "recession": 2, "stagflation": 3, "central bank buying": 3,
                 "record high": 2, "surge": 2, "rally": 2, "yields fall": 3, "yields drop": 3},
        "bear": {"rate hike": 4, "hikes rate": 4, "raise rates": 4, "hawkish": 3, "strong dollar": 3,
                 "dollar rises": 3, "dollar surges": 3, "yields rise": 3, "yields jump": 3,
                 "risk-on": 2, "risk on": 2, "taper": 2, "profit-taking": 2, "profit taking": 2,
                 "sells off": 2, "selloff": 2, "eases tension": 3, "ceasefire": 2, "cools": 1},
    },
    "EURUSD": {
        "label": "EUR / USD",
        "queries": [_q("EUR USD euro dollar forecast"), _q("ECB interest rate decision"),
                    _q("eurozone economy inflation"), _q("Federal Reserve dollar")],
        "bull": {"ecb hike": 4, "ecb raises": 4, "hawkish ecb": 4, "eurozone growth": 3,
                 "strong eurozone": 3, "euro rises": 3, "euro surges": 3, "dovish fed": 3,
                 "fed cut": 3, "fed cuts": 3, "weak dollar": 3, "dollar falls": 3, "risk-on": 2},
        "bear": {"ecb cut": 4, "ecb cuts": 4, "dovish ecb": 4, "weak eurozone": 3,
                 "eurozone recession": 3, "europe recession": 3, "euro falls": 3, "euro slips": 2,
                 "hawkish fed": 3, "fed hike": 3, "fed raises": 3, "strong dollar": 3,
                 "dollar rises": 3, "dollar surges": 3, "energy crisis": 3, "risk-off": 2},
    },
    "BTCUSD": {
        "label": "Bitcoin",
        "queries": [_q("bitcoin price"), _q("bitcoin ETF inflows"),
                    _q("crypto regulation SEC"), _q("bitcoin institutional adoption")],
        "bull": {"etf inflow": 4, "inflows": 3, "adoption": 3, "institutional": 3, "halving": 3,
                 "approval": 3, "approved": 3, "accumulat": 3, "record high": 3, "all-time high": 3,
                 "surge": 2, "rally": 2, "bullish": 2, "buys bitcoin": 3, "reserve": 2, "upgrade": 1},
        "bear": {"crackdown": 4, "ban": 3, "banned": 3, "hack": 4, "exploit": 3, "outflow": 3,
                 "outflows": 3, "lawsuit": 3, "sec sues": 4, "regulation": 2, "selloff": 3,
                 "sell-off": 3, "liquidation": 3, "crash": 4, "plunge": 3, "slump": 2, "fraud": 3},
    },
}

# Backward-compatible module-level oil lexicon (used by score_title default).
BULL = SYMBOLS["WTIUSD"]["bull"]
BEAR = SYMBOLS["WTIUSD"]["bear"]


def _negated(text, idx):
    """True if a negator appears in the ~22 chars before position idx."""
    window = text[max(0, idx - 22):idx]
    return any(neg in window for neg in NEGATORS)


def _apply(text, lex, sign, running):
    for term, w in lex.items():
        start = 0
        while True:
            i = text.find(term, start)
            if i < 0:
                break
            if not _negated(text, i):
                running += sign * w
            start = i + len(term)
    return running


def score_title(title, bull=None, bear=None):
    """Return (bias, score). Positive = bullish for the instrument. Negation-aware."""
    bull = BULL if bull is None else bull
    bear = BEAR if bear is None else bear
    t = " " + title.lower() + " "
    s = _apply(t, bull, +1, 0)
    s = _apply(t, bear, -1, s)
    return ("bullish" if s > 0 else "bearish" if s < 0 else "neutral"), s


def parse_rss(xml_bytes):
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:  # noqa: BLE001
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title:
            out.append({"title": title, "link": link, "pubdate": pub})
    return out


def _fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (feed)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:  # noqa: BLE001
        return None


def _signal(net):
    return "BUY" if net > 1 else "SELL" if net < -1 else "NEUTRAL"


def _strength(net, n):
    a = abs(net)
    if a >= 8 and n >= 6:
        return "HIGH"
    if a >= 3:
        return "MED"
    return "LOW"


def _why(signal, counts, net, headlines):
    top = headlines[:2]
    drivers = "; ".join(f"'{h['title'][:60]}' ({'+' if h['score'] > 0 else '-'})" for h in top)
    lean = {"BUY": "bullish", "SELL": "bearish", "NEUTRAL": "balanced"}[signal]
    base = (f"{signal} bias - news flow is {lean}: {counts['bullish']} bullish vs "
            f"{counts['bearish']} bearish headlines (net {net:+d}).")
    return base + (f" Main drivers: {drivers}." if drivers else "")


def build_symbol(cfg, timeout=15, per_source=10, keep=6):
    items, any_ok, seen = [], False, set()
    for url in cfg["queries"]:
        raw = _fetch(url, timeout)
        if raw is None:
            continue
        any_ok = True
        for it in parse_rss(raw)[:per_source]:
            key = it["title"].lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            bias, score = score_title(it["title"], cfg["bull"], cfg["bear"])
            items.append({**it, "bias": bias, "score": score})
    if not any_ok:
        return None
    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    net = 0
    for it in items:
        counts[it["bias"]] += 1
        net += it["score"]
    scored = sorted([i for i in items if i["score"] != 0], key=lambda i: -abs(i["score"]))[:keep]
    sig = _signal(net)
    res = {
        "label": cfg["label"],
        "signal": sig,
        "strength": _strength(net, len(items)),
        "net_bias": "bullish" if net > 1 else "bearish" if net < -1 else "mixed",
        "net_score": net,
        "counts": counts,
        "n_total": len(items),
        "why": _why(sig, counts, net, scored),
        "headlines": scored,
        "source": "lexicon",
    }
    # Optional upgrade: let Claude (your API key) judge the net bias.
    try:
        from engine import llm_news
        llm = llm_news.score_headlines(cfg["label"], [i["title"] for i in items])
        if llm:
            res["signal"] = llm["signal"]
            res["strength"] = llm["strength"]
            res["net_score"] = int(llm["score"])
            res["net_bias"] = ("bullish" if llm["score"] > 1 else "bearish" if llm["score"] < -1 else "mixed")
            res["why"] = "[Claude] " + llm.get("why", "")
            res["source"] = "claude-llm"
    except Exception:  # noqa: BLE001
        pass
    return res


def build_all(timeout=15, only=None):
    """Build the feed for all symbols, or just the ones in `only` (a set/list
    of symbol keys). `only` lets the live scheduler stay WTI-only and avoid
    spending analyst API credits on pairs that aren't being traded."""
    syms = {}
    for sym, cfg in SYMBOLS.items():
        if only and sym not in only:
            continue
        res = build_symbol(cfg, timeout=timeout)
        if res is not None:
            syms[sym] = res
    if not syms:
        return None
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asof": date.today().isoformat(),
        "source": "Google News RSS (negation-aware headline sentiment)",
        "symbols": syms,
    }


def write_all(path=FEED_PATH, **kw):
    data = build_all(**kw)
    if data is None:
        return None
    pathlib.Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def read_feed_raw(path=FEED_PATH):
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def load_feed(symbol="WTIUSD", path=FEED_PATH, max_age_days=3, today=None):
    if isinstance(symbol, (str, pathlib.PurePath)) and str(symbol).endswith(".json"):
        path, symbol = symbol, "WTIUSD"
    data = read_feed_raw(path)
    if not data:
        return None
    if "symbols" in data:
        asof = data.get("asof")
        entry = data["symbols"].get(symbol)
        if entry is None:
            return None
        entry = {**entry, "asof": asof}
    else:
        entry = data
        asof = entry.get("asof")
    try:
        d = date.fromisoformat(asof)
    except Exception:  # noqa: BLE001
        return None
    today = today or date.today()
    if (today - d).days > max_age_days:
        return None
    return entry


def render_lines(feed):
    c = feed["counts"]
    lines = [
        f"Signal: {feed.get('signal', '?')} ({feed.get('strength', '?')})  |  net bias "
        f"{feed['net_bias'].upper()} ({c['bullish']} bull / {c['bearish']} bear / "
        f"{c['neutral']} neutral, {feed['n_total']} headlines)",
        feed.get("why", ""),
    ]
    for h in feed["headlines"]:
        lines.append(f"[{h['bias'].upper()}] {h['title']}")
        if h.get("link"):
            lines.append("      " + h["link"])
    lines.append("Auto-scored headline sentiment - verify before trading.")
    return [x for x in lines if x]


if __name__ == "__main__":
    only = None
    try:
        from engine import config as _cfg
        raw = (_cfg.load().symbols or "").upper()
        picks = [x.strip() for x in raw.split(",") if x.strip() in SYMBOLS]
        only = picks or None
    except Exception:  # noqa: BLE001
        only = None
    data = write_all(only=only)
    if data is None:
        print("feed refresh FAILED (no network / all sources down) - notes use fallback.")
    else:
        print(f"fundamentals.json written | {data['generated']}")
        for sym, f in data["symbols"].items():
            print(f"  {sym} {f['label']:14s} -> {f['signal']:7s} {f['strength']:4s} "
                  f"net {f['net_score']:+d} ({f['n_total']} headlines)")


def feed_age_minutes(data, now=None):
    """Minutes since the feed was generated, or None if unknown/unparseable."""
    from datetime import datetime, timezone
    try:
        g = datetime.fromisoformat(data["generated"])
        now = now or datetime.now(timezone.utc)
        return (now - g).total_seconds() / 60.0
    except Exception:  # noqa: BLE001
        return None


def is_feed_stale(data, max_min=20, now=None):
    """True if the feed is older than max_min (or age unknown)."""
    age = feed_age_minutes(data, now=now)
    return age is None or age > max_min
