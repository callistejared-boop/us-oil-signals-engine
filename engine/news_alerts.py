"""Bias-flip alerter - turns the news feed from passive display into action.

Persists the last signal per pair; when a pair's signal genuinely flips to a
directional call (BUY/SELL) with at least MED strength, it fires one alert with
the reasoning. First run only records state (no spam); flips to NEUTRAL and
weak/low-strength changes are suppressed. DM-only by design.
"""
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "news_state.json"


def _load_state(path=STATE):
    try:
        d = json.loads(pathlib.Path(path).read_text())
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_state(state, path=STATE):
    p = pathlib.Path(path)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def detect_flips(feed, state):
    """Return (changes, new_state). A change is a meaningful directional flip."""
    changes = []
    new_state = dict(state)
    for sym, f in (feed.get("symbols") or {}).items():
        new = f.get("signal", "NEUTRAL")
        old = state.get(sym)
        new_state[sym] = new
        if old is not None and new != old and new in ("BUY", "SELL") \
                and f.get("strength") in ("MED", "HIGH"):
            changes.append({
                "sym": sym, "label": f.get("label", sym), "old": old, "new": new,
                "strength": f.get("strength", "?"), "why": f.get("why", ""),
                "headlines": f.get("headlines", []),
            })
    return changes, new_state


def build_alert_text(c):
    lines = [
        f"NEWS BIAS FLIP - {c['label']} ({c['sym']})",
        f"Was {c['old']}  ->  now {c['new']}  [{c['strength']} strength]",
        "",
        c["why"],
    ]
    if c["headlines"]:
        lines.append("")
        lines.append("Top headlines:")
        for h in c["headlines"][:3]:
            tag = h["bias"].upper()
            lines.append(f"[{tag}] {h['title']}")
            if h.get("link"):
                lines.append(h["link"])
    lines += ["", "Auto-scored news sentiment - a heads-up, not advice. Verify before trading."]
    return "\n".join(lines)


def run(feed, send_fn, state_path=STATE):
    """Detect flips vs saved state, send alerts via send_fn(text), persist state."""
    state = _load_state(state_path)
    changes, new_state = detect_flips(feed, state)
    for c in changes:
        try:
            send_fn(build_alert_text(c))
        except Exception as exc:  # noqa: BLE001
            print("alert send err:", exc)
    _save_state(new_state, state_path)
    return changes
