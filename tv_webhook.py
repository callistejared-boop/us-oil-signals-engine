"""Local TradingView webhook receiver.

TradingView (paid plan) POSTs alert JSON to this endpoint; it validates a shared
secret and appends to tradingview_signals.json, which the engine reads as a
small extra confirmation (engine.tv_signals). Expose to the internet with a
tunnel (e.g. ngrok) and set the TradingView alert's webhook URL to it.

Alert message JSON, e.g.:
  {"secret":"YOURSECRET","symbol":"XAUUSD","action":"buy"}

Set TV_WEBHOOK_SECRET (a random password) in your .env first.
"""
import json
import os
import pathlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
STORE = ROOT / "tradingview_signals.json"
PORT = int(os.environ.get("TV_WEBHOOK_PORT", "8899"))


def _secret():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("TV_WEBHOOK_SECRET"):
                return line.split("=", 1)[1].strip()
    return os.environ.get("TV_WEBHOOK_SECRET", "")


def _append(rec):
    try:
        data = json.loads(STORE.read_text())
        data = data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        data = []
    data.append(rec)
    STORE.write_text(json.dumps(data[-200:], indent=2), encoding="utf-8")


class _H(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(n).decode("utf-8", "replace")
        try:
            p = json.loads(body)
        except Exception:  # noqa: BLE001
            p = {}
        ok = bool(_secret()) and p.get("secret") == _secret()
        if ok and p.get("symbol") and p.get("action"):
            _append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "symbol": str(p["symbol"]).upper(), "action": str(p["action"]).lower()})
        self.send_response(200 if ok else 401)
        self.end_headers()
        self.wfile.write(b"ok" if ok else b"unauthorized")

    def log_message(self, *a):  # silence
        pass


def main():
    if not _secret():
        print("Set TV_WEBHOOK_SECRET=<a random password> in your .env first. Aborting.")
        return
    print(f"TradingView webhook receiver listening on port {PORT}.")
    print(f"Point your TradingView alert webhook at http://<this-host>:{PORT}/  "
          "(use a tunnel like ngrok for internet access). Ctrl+C to stop.")
    HTTPServer(("0.0.0.0", PORT), _H).serve_forever()


if __name__ == "__main__":
    main()
