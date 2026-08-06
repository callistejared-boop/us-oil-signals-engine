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
    # --- Day 3: portfolio risk engine (see RISK_SPECIFICATION.md) -----------
    "portfolio_equity", "portfolio_risk_mode", "portfolio_max_risk_pct",
    "portfolio_day_stop_r", "portfolio_max_drawdown_r", "portfolio_max_directional",
    "correlation_high_threshold", "correlation_window_days",
    # --- Day 4: market regime engine (see MARKET_REGIME_SPECIFICATION.md) ---
    "regime_filter_mode", "regime_min_quality_for_block", "regime_strategy",
    # --- Day 6: confidence engine (see CONFIDENCE_ENGINE_SPECIFICATION.md) --
    "confidence_tier_low", "confidence_tier_moderate", "confidence_tier_high",
    "confidence_tier_exceptional",
    # --- V2.2 Priority 1 Item 3: execution profile style (see
    # engine/execution/execution_profile.py) ---------------------------------
    "execution_style",
]


def _coerce(current, raw: str):
    """Cast an incoming string (.env line or os.environ value) to match the
    type of the dataclass default it is overriding. Extracted as its own
    function on 2026-08-03 (Day 3) because the original inline
    `int(val) if isinstance(cur, int) else val` silently left float-typed
    settings (portfolio_equity, portfolio_max_risk_pct, ...) as raw strings,
    which would have broken arithmetic the first time a float field was
    added. bool is checked before int because bool is a subclass of int in
    Python — without that ordering a bool field would be coerced by the int
    branch and always evaluate truthy for any non-empty string."""
    if isinstance(current, bool):
        return bool(int(raw))
    if isinstance(current, int):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    return raw


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
    # --- Day 3: portfolio risk engine (see RISK_SPECIFICATION.md) -----------
    # Notional account size used ONLY for portfolio-risk aggregation math.
    # No module in this codebase reads a live broker balance; operators
    # running real forward-test capital should override this via .env /
    # PORTFOLIO_EQUITY to match their actual account size, or portfolio
    # exposure percentages will be computed against the wrong base.
    portfolio_equity: float = 10000.0
    # "block": a hard portfolio-risk violation prevents publication (default,
    #   per the explicit Day 3 mandate: "the trade must be rejected before
    #   publication"). "warn": violations are logged/ledgered but do not
    #   block — a shadow-mode escape hatch an operator can use to gather
    #   evidence before trusting a newly-added check, consistent with the
    #   platform's standing "prove it before it gets teeth" discipline
    #   (see range_guard.py's SUPPRESS_MODE precedent).
    portfolio_risk_mode: str = "block"
    # Matches engine.risk.MAX_PORTFOLIO_RISK_PCT (6.0). Kept as a separate,
    # config-overridable field rather than importing engine.risk here to
    # avoid adding a dependency to this low-level module; test_portfolio_risk
    # asserts the two stay in sync so they cannot silently drift apart.
    portfolio_max_risk_pct: float = 6.0
    # Account-wide daily loss stop across ALL symbols combined. RISK_RULES.md
    # rule #2 documents "-2R" as an account-level rule; risk_guard.py
    # deliberately implements it per-symbol only (2026-07-28 fix, so one bad
    # gold day doesn't lock out oil). This field is the portfolio-wide
    # backstop that reconciles the documented rule with the per-symbol code
    # — see RISK_SPECIFICATION.md §5 for the full reasoning.
    portfolio_day_stop_r: float = 2.0
    # Trailing 30-closed-trade portfolio-wide drawdown cap, matching
    # RISK_RULES.md's documented "keep under 6R per 30-trade window" rule
    # (same 6.0 figure the Day 1 audit already validated — not a new number).
    portfolio_max_drawdown_r: float = 6.0
    # Max number of simultaneous open positions in the SAME direction across
    # ALL symbols before same-direction concentration is flagged.
    portfolio_max_directional: int = 2
    # |correlation| above this is treated as "meaningfully correlated" for
    # concentration checks (engine.correlation_dynamic).
    correlation_high_threshold: float = 0.6
    # Rolling window (trading days) for dynamic correlation estimation.
    correlation_window_days: int = 60
    # --- Day 4: market regime engine -----------------------------------------
    # "advisory": regime classification runs, is logged/recorded to
    #   regime_history.jsonl and the ledger on every scan, but never blocks
    #   publication (default — no forward-test evidence yet that regime
    #   filtering improves expectancy; see MARKET_REGIME_SPECIFICATION.md
    #   §7 "Statistical Validation Plan"). "block": a new HEADS-UP is
    #   suppressed when regime_quality_score < regime_min_quality_for_block.
    #   Only ever gates NEW setup origination (Stage-1), never an
    #   already-published Stage-2 ENTRY fill.
    regime_filter_mode: str = "advisory"
    regime_min_quality_for_block: int = 30
    # Which entry in engine.regime_engine.STRATEGY_COMPATIBILITY to score
    # the current regime against. The platform has one production strategy
    # today; this is config-driven so a second strategy is a value change,
    # not a code change.
    regime_strategy: str = "ict_smc_mast"
    # --- Day 6: confidence engine decision tiers (see
    # CONFIDENCE_ENGINE_SPECIFICATION.md) --------------------------------------
    # Boundaries for engine.confidence_engine's five-tier classification of
    # the composite `overall_confidence` score (0-100). Chosen to align with,
    # not contradict, thresholds this platform already publishes against:
    # 70 matches signals.PUBLISH_THRESHOLD and confluence_min_score's default
    # (the existing "confirmed/tradeable" bar); 55 matches
    # signals.WATCH_THRESHOLD (the existing "worth watching" bar); 85 and 40
    # are new intermediate bands, chosen to roughly mirror grade.py's A/B/C
    # spacing rather than an arbitrary split. Not statistically fitted —
    # engineering-judgment defaults, disclosed as such, overridable via .env.
    confidence_tier_low: int = 40           # < this -> "Research Only"
    confidence_tier_moderate: int = 55      # >= this -> "Moderate Confidence"
    confidence_tier_high: int = 70          # >= this -> "High Confidence"
    confidence_tier_exceptional: int = 85   # >= this -> "Exceptional Confidence"
    # --- V2.2 Priority 1 Item 3: which named tolerance profile (see
    # engine.execution.execution_profile.PROFILES: "swing" | "day" |
    # "scalping") the live Execution Simulator evaluates every fill
    # against. The platform has one production strategy today, same
    # posture as regime_strategy above; this is config-driven so a second,
    # differently-styled strategy is a value change, not a code change.
    # Superseded per-strategy once the Strategy Registry (V2.2, not yet
    # built) exists - this single global setting is the deliberate,
    # disclosed interim source until then.
    execution_style: str = "day"


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
                setattr(s, key, _coerce(cur, val))
    # Env vars override the file (CI/cloud runners set secrets this way).
    for field_name in _FIELDS:
        raw = os.environ.get(field_name.upper())
        if raw is not None and raw != "":
            cur = getattr(s, field_name)
            setattr(s, field_name, _coerce(cur, raw))
    for key, val in os.environ.items():
        if key.upper().startswith("TELEGRAM_CHANNEL_") and val:
            s.symbol_channels[key.upper()[len("TELEGRAM_CHANNEL_"):]] = val
    return s
