"""Claude-powered news analyst (optional upgrade over the keyword lexicon).

When ANTHROPIC_API_KEY is set in .env, this asks Claude to read a pair's recent
headlines and return a proper BUY/SELL/NEUTRAL call with strength, a numeric
score, and a one-line rationale. Runs on YOUR laptop with YOUR key (uses your
credits). Fail-safe: no key/headlines/error -> None and the feed uses the
transparent keyword lexicon instead. Model configurable via LLM_MODEL.
"""
import json
import os
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def _env(key, default=""):
    v = os.environ.get(key)
    if v:
        return v.strip()
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return default


def available():
    return bool(_env("ANTHROPIC_API_KEY"))


def _norm_sig(s):
    s = str(s).upper()
    if "BUY" in s or "LONG" in s or "BULL" in s:
        return "BUY"
    if "SELL" in s or "SHORT" in s or "BEAR" in s:
        return "SELL"
    if "NEUTRAL" in s or "HOLD" in s or "FLAT" in s or "MIXED" in s:
        return "NEUTRAL"
    return ""


def _norm_str(s):
    s = str(s).upper()
    if "HIGH" in s or "STRONG" in s:
        return "HIGH"
    if "LOW" in s or "WEAK" in s:
        return "LOW"
    return "MED"


def _norm_score(v):
    try:
        return max(-10, min(10, int(round(float(str(v).split("/")[0].strip().lstrip("+"))))))
    except Exception:  # noqa: BLE001
        return 0


def _parse(text):
    """Tolerant: extract a JSON object and normalise fields. None if no signal."""
    if not text:
        return None
    raw = None
    try:
        i, j = text.index("{"), text.rindex("}")
        raw = json.loads(text[i:j + 1])
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, dict):
        return None
    sig = _norm_sig(raw.get("signal", ""))
    if not sig:
        return None
    return {"signal": sig, "strength": _norm_str(raw.get("strength", "MED")),
            "score": _norm_score(raw.get("score", 0)),
            "why": str(raw.get("why", ""))[:160], "source": "claude-llm"}


def _write_diag(msg):
    try:
        (ROOT / "llm_diag.txt").write_text(msg, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def score_headlines(label, titles, timeout=30):
    key = _env("ANTHROPIC_API_KEY")
    titles = [t for t in (titles or []) if t][:15]
    if not key or not titles:
        return None
    model = _env("LLM_MODEL", DEFAULT_MODEL)
    prompt = (
        f"You are a professional markets analyst. For {label}, read these recent "
        "headlines and judge the NET directional bias FOR THIS INSTRUMENT over the "
        "next 1-2 sessions. Weigh supply/demand, macro (rates/USD), and geopolitics; "
        "account for negations (a denied event is not the event).\n"
        "Reply with ONLY a JSON object, no prose, no code fences:\n"
        '{"signal":"BUY|SELL|NEUTRAL","strength":"LOW|MED|HIGH","score":<integer -10..10, '
        '+ = bullish>,"why":"<=18 words"}\n\nHeadlines:\n'
        + "\n".join("- " + t for t in titles)
    )
    body = json.dumps({"model": model, "max_tokens": 200,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        res = _parse(text)
        if res is None:
            _write_diag("PARSE-FAIL for " + str(label) + " reply:\n" + text[:600])
        return res
    except Exception as exc:  # noqa: BLE001
        _write_diag("CALL-ERROR for " + str(label) + ": " + repr(exc)[:400])
        return None


def _diag():
    import urllib.error
    key = _env("ANTHROPIC_API_KEY")
    model = _env("LLM_MODEL", DEFAULT_MODEL)
    out = [f"key len {len(key)} | model {model}"]
    titles = ["US strikes Iran, Strait of Hormuz shipping halted", "OPEC weighs deeper output cut"]
    prompt = ('Reply ONLY with JSON: {"signal":"BUY|SELL|NEUTRAL","strength":"LOW|MED|HIGH",'
              '"score":<int -10..10>,"why":"<=18 words"}\nHeadlines:\n' + "\n".join("- " + t for t in titles))
    body = json.dumps({"model": model, "max_tokens": 200,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        out.append("RAW REPLY: " + text[:400])
        out.append("PARSED: " + repr(_parse(text)))
    except urllib.error.HTTPError as e:
        out.append(f"HTTP {e.code}: " + e.read().decode("utf-8", "replace")[:400])
    except Exception as e:  # noqa: BLE001
        out.append(f"{type(e).__name__}: {e}")
    _write_diag("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    _diag()
