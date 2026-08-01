"""Live News & Bias interface -> news_bias.html.

Reads fundamentals.json (written by engine.fundamentals_feed) and renders a
per-pair panel: a BUY / SELL / NEUTRAL badge, the reasoning, and the scored
headlines with source links. The page self-reloads every 5 minutes. A
STALE-FEED watchdog banner appears if the underlying data hasn't refreshed in
over 20 minutes - so a silently-dead 5-minute job can't fool you with old data.
"""
import html
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from engine import fundamentals_feed as ff  # noqa: E402

BADGE = {"BUY": "#1f9d55", "SELL": "#e0526a", "NEUTRAL": "#8b93a3"}


def _age(generated):
    try:
        g = datetime.fromisoformat(generated)
        secs = (datetime.now(timezone.utc) - g).total_seconds()
        if secs < 90:
            return "just now"
        if secs < 3600:
            return f"{int(secs//60)} min ago"
        return f"{int(secs//3600)}h ago"
    except Exception:  # noqa: BLE001
        return "unknown"


def card(sym, f):
    sig = f.get("signal", "NEUTRAL")
    col = BADGE.get(sig, "#8b93a3")
    c = f.get("counts", {})
    heads = ""
    for h in f.get("headlines", []):
        hc = "#38c172" if h["bias"] == "bullish" else "#e0526a" if h["bias"] == "bearish" else "#8b93a3"
        title = html.escape(h["title"])
        link = html.escape(h.get("link", ""))
        t = f"<a href='{link}' target='_blank' rel='noopener'>{title}</a>" if link else title
        heads += (f"<li><span class='tag' style='color:{hc}'>{h['bias'][:4].upper()}</span> "
                  f"<span class='sc'>{h['score']:+d}</span> {t}</li>")
    if not heads:
        heads = "<li class='muted'>No scored headlines yet - run a refresh.</li>"
    strength = f.get("strength", "")
    sbadge = f"<span class='str'>{strength}</span>" if strength else ""
    return (f"<div class='card'><div class='top'><div class='pair'>{html.escape(f.get('label', sym))}"
            f"<span class='sym'>{sym}</span></div>"
            f"<div class='badge' style='background:{col}'>{sig} {sbadge}</div></div>"
            f"<div class='counts'>net {f.get('net_score', 0):+d} &middot; "
            f"{c.get('bullish', 0)} bull / {c.get('bearish', 0)} bear / {c.get('neutral', 0)} neutral "
            f"&middot; {f.get('n_total', 0)} headlines</div>"
            f"<div class='why'>{html.escape(f.get('why', ''))}</div>"
            f"<ul class='heads'>{heads}</ul></div>")


def render(data):
    banner = ""
    if not data or "symbols" not in data or not data["symbols"]:
        body = ("<div class='card'><div class='why'>No live data yet. Run "
                "<b>Refresh live fundamentals</b> (START_HERE option 10) or schedule the "
                "5-minute refresh (option 12) to populate this page.</div></div>")
        gen, age = "-", "-"
    else:
        body = "".join(card(s, f) for s, f in data["symbols"].items())
        gen = html.escape(data.get("generated", "-"))
        age = _age(data.get("generated", ""))
        if ff.is_feed_stale(data, max_min=20):
            mins = ff.feed_age_minutes(data)
            howold = f"{int(mins)} min ago" if mins is not None else "an unknown time ago"
            banner = ("<div class='stale'>&#9888; FEED STALE - last refreshed " + howold
                      + ". The 5-minute job may have stopped. Re-run START_HERE &rarr; 10, "
                      "or check the 'Signals News 5min' scheduled task.</div>")
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta http-equiv='refresh' content='300'>"
        "<title>Live News & Bias</title><style>"
        "body{font-family:-apple-system,'Segoe UI',system-ui,sans-serif;background:#0b0e14;color:#e7eaf0;max-width:1000px;margin:16px auto;padding:0 14px}"
        "h1{color:#e6b312;margin:0 0 2px}.sub{color:#8b93a3;font-size:12.5px;margin-bottom:14px}"
        ".stale{background:#3a1616;border:1px solid #e0526a;color:#ffb3bd;border-radius:10px;padding:10px 14px;font-size:13px;font-weight:600;margin-bottom:12px}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}"
        ".card{background:#141a24;border:1px solid #232c3a;border-radius:14px;padding:14px}"
        ".top{display:flex;justify-content:space-between;align-items:center}"
        ".pair{font-weight:800;font-size:16px}.sym{color:#8b93a3;font-weight:500;font-size:11px;margin-left:6px}"
        ".badge{color:#fff;font-weight:800;font-size:14px;padding:4px 12px;border-radius:8px;letter-spacing:.5px}"
        ".str{font-size:9px;opacity:.85;font-weight:700}"
        ".counts{color:#8b93a3;font-size:11.5px;margin:6px 0}"
        ".why{font-size:13px;line-height:1.5;background:#0f131b;border-radius:8px;padding:9px 11px;margin-bottom:8px}"
        ".heads{list-style:none;padding:0;margin:0}"
        ".heads li{font-size:12.5px;padding:5px 0;border-top:1px solid #1c2432;line-height:1.45}"
        ".tag{font-weight:800;font-size:10px;margin-right:4px}.sc{color:#6b7280;font-size:10px;margin-right:4px}"
        ".heads a{color:#cfe0ff;text-decoration:none}.heads a:hover{text-decoration:underline}"
        ".muted{color:#8b93a3}"
        ".disc{background:#1a1608;border:1px solid #3a3113;border-radius:10px;padding:11px 14px;font-size:11.5px;color:#d8c58c;margin-top:16px}"
        "</style></head><body>"
        "<h1>Live News &amp; Bias</h1>"
        f"<div class='sub'>Updated {age} &middot; generated {gen} &middot; page auto-reloads every 5 min. "
        "Signals are auto-scored news sentiment - a decision aid, not certainty.</div>"
        f"{banner}"
        f"<div class='grid'>{body}</div>"
        "<div class='disc'>&#9888; Bias is derived from negation-aware headline-sentiment scoring across "
        "public financial news feeds (Reuters/Bloomberg/CNBC/FT via Google News). It is a heuristic aid, "
        "not financial advice. Always confirm against the primary source before trading.</div>"
        "</body></html>")


def main():
    data = ff.read_feed_raw()
    (ROOT / "news_bias.html").write_text(render(data), encoding="utf-8")
    n = len(data["symbols"]) if data and "symbols" in data else 0
    print(f"wrote news_bias.html | {n} pairs")


if __name__ == "__main__":
    main()
