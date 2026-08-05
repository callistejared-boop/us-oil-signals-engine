"""Day 11 — Curated macro reference data: central bank policy stance,
geopolitical flags, and known economic-print history.

Some macro facts are genuinely NOT live-tickers — a central bank's policy
stance, the outcome of the last CPI print, whether an active geopolitical
supply-shock narrative is underway. Institutional macro desks maintain
these as CURATED assessments, updated on a schedule (after each central
bank meeting, each data release), not scraped continuously. Forcing this
into a live-fetch shape would either require an expensive commercial data
subscription (out of scope) or risk fabricating precision this platform
cannot actually verify — this codebase's standing discipline (Day 6's
`probability_label`, Day 9's `sharpe_like`/`sortino_like` naming, Day 9's
`evidence_tiers.py`) is to disclose a limitation honestly rather than
paper over it with invented numbers.

DESIGN, mirroring `engine/eia_feed.py`'s established precedent exactly
(the one other module in this codebase that already needs operator-
supplied configuration rather than a pure live fetch): without a
populated reference file, every function here returns a clearly-labeled
"not configured" result and the rest of the pipeline is completely
unaffected — never raises, never blocks, never silently assumes a stance.
`macro_reference.json` ships with a single illustrative example entry per
section, explicitly marked `"example": true`, NOT asserted as a verified
real-world fact — an operator replaces it with their own curated,
sourced, dated entries. See MACRO_ENGINE_SPECIFICATION.md Sec.4 for the
recommended update cadence and sourcing guidance.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
REFERENCE_PATH = ROOT / "macro_reference.json"

CENTRAL_BANKS = ["Federal Reserve", "ECB", "BOE", "BOJ", "PBOC"]

_DEFAULT = {
    "central_banks": {
        "Federal Reserve": {
            "stance": "unknown", "expected_direction": "unknown",
            "uncertainty": "not_configured", "next_scheduled_event": "",
            "updated": "", "source": "", "example": True,
            "note": "Populate via operator update — see MACRO_ENGINE_SPECIFICATION.md Sec.4",
        },
    },
    "geopolitical_flags": [
        {
            "category": "energy_supply_disruption", "region": "example",
            "severity": "unknown", "affected_assets": ["WTIUSD"],
            "summary": "Illustrative placeholder — replace with a real, sourced, dated entry.",
            "updated": "", "source": "", "example": True,
        },
    ],
    "economic_prints": {
        "CPI": {"last_value": None, "prior_value": None, "period": "",
                "surprise": "unknown", "updated": "", "source": "", "example": True},
        "NFP": {"last_value": None, "prior_value": None, "period": "",
                "surprise": "unknown", "updated": "", "source": "", "example": True},
        "unemployment_rate": {"last_value": None, "prior_value": None, "period": "",
                              "surprise": "unknown", "updated": "", "source": "", "example": True},
    },
}


def _load() -> dict:
    try:
        return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return _DEFAULT


def ensure_reference_file() -> None:
    """Writes the illustrative default reference file if none exists yet.
    Never overwrites an operator-populated file. Never raises."""
    try:
        if not REFERENCE_PATH.exists():
            REFERENCE_PATH.write_text(json.dumps(_DEFAULT, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def central_bank_stance(bank: str) -> dict:
    """Returns the curated stance for one bank, or a clearly-labeled
    not-configured result for a bank with no entry / unrecognized name.
    Never raises."""
    try:
        entry = _load().get("central_banks", {}).get(bank)
        if not entry:
            return {"bank": bank, "configured": False, "stance": "unknown",
                    "expected_direction": "unknown", "uncertainty": "not_configured",
                    "next_scheduled_event": "", "note": f"no reference entry for {bank}"}
        out = dict(entry)
        out["bank"] = bank
        out["configured"] = not out.get("example", False)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"bank": bank, "configured": False, "stance": "unknown",
                "expected_direction": "unknown", "uncertainty": "error",
                "next_scheduled_event": "", "note": f"error: {exc}"}


def all_central_bank_stances() -> dict:
    return {bank: central_bank_stance(bank) for bank in CENTRAL_BANKS}


def geopolitical_flags(symbol: str = None) -> list:
    """Curated geopolitical flags, optionally filtered to those whose
    `affected_assets` include `symbol`. Never raises."""
    try:
        flags = _load().get("geopolitical_flags", [])
        if symbol:
            flags = [f for f in flags if symbol in (f.get("affected_assets") or [])]
        return flags
    except Exception:  # noqa: BLE001
        return []


def economic_print(name: str) -> dict:
    """Curated last-known print for a named series (e.g. 'CPI', 'NFP',
    'unemployment_rate'). Never raises."""
    try:
        entry = _load().get("economic_prints", {}).get(name)
        if not entry:
            return {"series": name, "configured": False, "last_value": None,
                    "note": f"no reference entry for {name}"}
        out = dict(entry)
        out["series"] = name
        out["configured"] = not out.get("example", False)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"series": name, "configured": False, "last_value": None, "note": f"error: {exc}"}


def update_central_bank(bank: str, *, stance: str, expected_direction: str,
                        uncertainty: str, next_scheduled_event: str = "",
                        source: str = "") -> dict:
    """Operator-facing update helper — writes one bank's curated stance.
    Not called from any live trading path; a deliberate, explicit action
    an operator (or a future admin tool) takes. Never raises."""
    try:
        data = _load()
        data.setdefault("central_banks", {})
        data["central_banks"][bank] = {
            "stance": stance, "expected_direction": expected_direction,
            "uncertainty": uncertainty, "next_scheduled_event": next_scheduled_event,
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source, "example": False,
        }
        REFERENCE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"ok": True, "bank": bank}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
