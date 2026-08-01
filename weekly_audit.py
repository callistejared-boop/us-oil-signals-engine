"""Weekly self-audit -> Telegram DM (private). Recomputes what predicts wins
from the live journal and messages you the recommendations. DM only, never the
public channel. Run with no args to preview, --send to post.
"""
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent
import sys as _sys
_sys.path.insert(0, str(ROOT))
from engine import store as _store
rows = _store.load_array(ROOT / "trades.json")
closed = [r for r in rows if r.get("status") in ("win", "loss", "scratch")]


def seg(rs):
    n = len(rs)
    w = [x for x in rs if x > 1e-9]
    l = [x for x in rs if x < -1e-9]
    gl = abs(sum(l))
    return {"n": n, "wr": (len(w) / n if n else 0), "net": sum(rs),
            "exp": (sum(rs) / n if n else 0), "pf": (sum(w) / gl if gl else 0)}


def bucket(c):
    c = int(c or 0)
    return "90-95" if c >= 90 else "80-89" if c >= 80 else "70-79" if c >= 70 else "<70"


ov = seg([r["result_r"] for r in closed])
mk = defaultdict(list)
cf = defaultdict(list)
for r in closed:
    mk[r.get("symbol", "?")].append(r["result_r"])
    cf[bucket(r.get("confidence"))].append(r["result_r"])
mk = {k: seg(v) for k, v in mk.items()}
cf = {k: seg(v) for k, v in cf.items()}

lines = ["WEEKLY SELF-AUDIT - what the engine is learning",
         f"{ov['n']} closed trades - win {ov['wr']*100:.0f}% - net {ov['net']:+.1f}R - PF {ov['pf']:.2f}", ""]
big = [(k, v) for k, v in mk.items() if v["n"] >= 5 and k != "?"]
if big:
    best = max(big, key=lambda kv: kv[1]["exp"])
    worst = min(big, key=lambda kv: kv[1]["exp"])
    lines.append("Best market: " + str(best[0]) + f" (exp {best[1]['exp']:+.2f}R, n={best[1]['n']})")
    lines.append("Weakest market: " + str(worst[0]) + f" (exp {worst[1]['exp']:+.2f}R, n={worst[1]['n']})")
order = [b for b in ["90-95", "80-89", "70-79", "<70"] if b in cf]
if len(order) >= 2:
    hi, lo = cf[order[0]]["wr"], cf[order[-1]]["wr"]
    if lo > hi + 0.05:
        lines.append("NOTE: confidence score currently inverted (low bucket wins more) - monitoring, not rewiring.")
    elif hi > lo + 0.05:
        lines.append("Confidence score is predictive - trusting it more when sizing.")
lines += ["", "Transparent by design - nothing auto-changes; these are flags for review.",
          "Research/education only."]
msg = "\n".join(lines)
print(msg)

if "--send" in sys.argv:
    try:
        sys.path.insert(0, str(ROOT))
        from engine import config
        import urllib.parse
        import urllib.request
        s = config.load()
        data = urllib.parse.urlencode({"chat_id": s.telegram_chat_id, "text": msg}).encode()
        urllib.request.urlopen("https://api.telegram.org/bot" + s.telegram_bot_token + "/sendMessage",
                               data=data, timeout=25)
        print("\n[sent to your DM]")
    except Exception as exc:  # noqa: BLE001
        print("send err:", exc)
