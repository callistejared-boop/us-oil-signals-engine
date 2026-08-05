"""Confluence history — append-only JSONL record of every MAST confluence
read's structured explanation and quality score. Day 5.

Mirrors engine/ledger.py's and engine/regime_history.py's exact
append/rotate/tail pattern rather than inventing a new persistence
mechanism. This is the dataset the Day 5 mandate's Phase 3/9 contribution
measurement and Phase 4 adaptive-weighting recommendations need — it did
not exist before Day 5, so it starts empty and only becomes useful once
enough closed, confluence-tagged trades accumulate (see
RESEARCH_CONFLUENCE_ENGINE.md for the honest current-data assessment).

Why a separate store from `regime_history.jsonl` / `trades.json` rather
than extending either: `journal.py`'s `Trade` dataclass already stores an
aggregate `confluence_score`/`confluence_agree` (count only, no per-source
detail) — extending its schema further is the same category of deferred
decision as Day 3's `risk_cash` gap and Day 4's regime-taxonomy gap (schema
changes are out of scope for a single day's "integration, not a redesign").
This store is purely additive and joins to `trades.json` by nearest
timestamp (see `confluence_analysis.join_trades_with_confluence`), the same
strategy Day 4 already established for regime data.
"""
import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "confluence_history.jsonl"
MAX_LINES = 20000


def _read_all() -> list:
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:  # noqa: BLE001
        return []


def _rotate() -> None:
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            HISTORY_PATH.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def record(symbol: str, direction: str, cr_score: int, cr_final_tier: str,
          agree: list, disagree: list, quality: dict, conflicts: list,
          ref: str = "") -> dict:
    """Append one confluence read's outcome-relevant fields. `ref` (Day 6,
    optional, keyword-only-by-convention/default "" so every pre-existing
    positional call site is unaffected) is the stable trade-journal
    reference — see journal.make_ref() — enabling a direct lookup instead
    of the nearest-timestamp join when the caller knows it (Stage-2 ENTRY
    reads do; Stage-1 heads-up reads, which may never become a trade, pass
    ""). Never raises; returns the record that would have been written even
    if the write itself failed (matching ledger.py's fail-safe posture)."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": symbol, "direction": direction,
        "score": cr_score, "final_tier": cr_final_tier,
        "agree": list(agree or []), "disagree": list(disagree or []),
        "quality_score": (quality or {}).get("score"),
        "n_conflicts": len(conflicts or []),
        "ref": ref or "",
    }
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        _rotate()
    except Exception:  # noqa: BLE001
        pass
    return rec


def tail(n: int = 20, symbol: str = None) -> list:
    rows = _read_all()
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    return rows[-n:]


def all_rows() -> list:
    """Full history — the input to join_trades_with_confluence()."""
    return _read_all()


def find_by_ref(ref: str) -> dict | None:
    """Day 6: direct stable-reference lookup, the preferred alternative to
    join_trades_with_confluence()'s nearest-timestamp join whenever `ref`
    is non-empty (see journal.make_ref() / Trade.confluence_ref)."""
    if not ref:
        return None
    for r in reversed(_read_all()):
        if r.get("ref") == ref:
            return r
    return None
