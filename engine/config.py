"""Settings loaded from a plain .env file next to the project root, with
real OS environment variables (e.g. GitHub Actions / cloud-runner secrets)
taking priority over the file. This lets the exact same code run unchanged
on a laptop (.env file) or in CI (secrets injected as env vars, no file).

Per-symbol channels: any key TELEGRAM_CHANNEL_<SYMBOL> (e.g.
TELEGRAM_CHANNEL_WTIUSD) routes that symbol's messages to its own channel;
everything else falls back to TELEGRAM_CHANNEL.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_FIELDS = [
    "telegram_bot_token", "telegram_chat_id", "telegram_channel",
    "twelvedata_api_key", "symbols", "data_csv", "scan_interval_seconds",
    "paper_mode", "max_daily_loss_r", "max_open_per_symbol",
    "confluence_min_score", "eia_api_key",
]


@dataclass
class Settings:
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_channel: str = ""
    twelvedata_api_key: str = ""
    symbols: str = ""
    data_csv: str = str(ROOT / "data" / "XAU_15m_data.csv")
    scan_interval_seconds: int = 900
    symbol_channels: dict = field(default_factory=dict)
    # --- risk & validation discipline (see RISK_RULES.md) -------------------
    paper_mode: int = 1            # 1 = forward-test: alerts tagged PAPER
    max_daily_loss_r: int = 2      # stop publishing new signals after -2R day
    max_open_per_symbol: int = 1   # never stack positions in one market
    confluence_min_score: int = 70  # MAST: min weighted score to keep "confirmed"
    eia_api_key: str = ""          # optional: real EIA crude inventory data (free key)


def load(path: Path | None = None) -> Settings:
    env = path or ROOT / ".env"
    s = Settings()
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip().lower()
            val = val.strip().strip('"').strip("'")
            if key.startswith("telegram_channel_"):
                sym = key[len("telegram_channel_"):].upper()
                s.symbol_channels[sym] = val
            elif hasattr(s, key):
                cur = getattr(s, key)
                setattr(s, key, int(val) if isinstance(cur, int) else val)
    # Env vars override the file (CI/cloud runners set secrets this way).
    for field_name in _FIELDS:
        raw = os.environ.get(field_name.upper())
        if raw is not None and raw != "":
            cur = getattr(s, field_name)
            setattr(s, field_name, int(raw) if isinstance(cur, int) else raw)
    for key, val in os.environ.items():
        if key.upper().startswith("TELEGRAM_CHANNEL_") and val:
            s.symbol_channels[key.upper()[len("TELEGRAM_CHANNEL_"):]] = val
    return s
