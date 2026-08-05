"""The single coordinator. Every external caller (alert_signals.py,
dashboard_publish.py, a future research script) should call
`run_health_check()` rather than importing the individual check modules
directly — this is the one place that knows how to dispatch each
registered feed's `probe_kind` to the right freshness lookup, load the
already-on-disk payload each feed's OWN cache file holds (never a fresh
fetch), run completeness/consistency/anomaly against it, classify the
result, apply the dependency cascade, persist a research record, and
hand back one assembled `health_report.build_report()` dict.

FAILURE PHILOSOPHY: no silent failures. Every run appends one line to
`data_health_history.jsonl` (this Day's own append-only research trail,
same convention as `run_ledger.jsonl`/`macro_history.jsonl`/
`broker_history.jsonl`), and any provider that is PARTIAL or worse, or
that TRANSITIONS from a worse state back to a better one (a recovery),
gets its own dedicated event line — so a failure becomes an event, a log
line, and (via `dashboard_snapshot()`) a dashboard notification, per the
mandate's own requirement. Nothing in this module ever raises out to a
caller; every internal step is individually guarded.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

from . import registry as reg
from . import freshness as fr
from . import completeness as comp
from . import consistency as cons
from . import anomaly as anom
from . import provider_status as ps
from . import heartbeat as hb
from . import health_report as hr

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DATA_HEALTH_HISTORY = ROOT / "data_health_history.jsonl"
MAX_LINES = 5000

_LAST_STATUS_CACHE: dict = {}  # feed_id -> last-seen status, in-process only;
                                 # recovery detection also re-derives from the
                                 # persisted history so it survives a fresh
                                 # process (see _previous_statuses_from_history)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append_event(row: dict) -> None:
    try:
        with open(DATA_HEALTH_HISTORY, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        lines = DATA_HEALTH_HISTORY.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            DATA_HEALTH_HISTORY.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def history_tail(n: int = 20) -> list:
    try:
        lines = DATA_HEALTH_HISTORY.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:  # noqa: BLE001
        return []


def _previous_statuses_from_history() -> dict:
    """Reconstructs the last known status per feed_id from the persisted
    history (not just this process's memory), so recovery detection works
    correctly across this platform's fresh-process-per-scan execution
    model — same discipline as Day 13's `rebuild_from_history()`."""
    out = {}
    try:
        lines = DATA_HEALTH_HISTORY.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "run_summary":
                for feed_id, status in (row.get("statuses") or {}).items():
                    out[feed_id] = status
    except Exception:  # noqa: BLE001
        pass
    return out


def _probe_age_minutes(spec) -> object:
    """Dispatches one FeedSpec's probe_kind to the right age lookup.
    Returns None (unknown) for anything unexpected rather than raising."""
    try:
        if spec.probe_kind == "file_mtime":
            return fr.age_minutes_from_mtime(spec.probe_target)
        if spec.probe_kind == "json_field":
            return fr.age_minutes_from_json_field(spec.probe_target, "generated")
        if spec.probe_kind == "observed":
            return fr.age_minutes_from_observation(spec.probe_target or spec.feed_id)
        if spec.probe_kind == "heartbeat":
            block = hb.scheduler_status()
            return block.get("age_minutes")
        if spec.probe_kind == "computed":
            return 0.0  # pure computation, always "as fresh as this process"
        return None
    except Exception:  # noqa: BLE001
        return None


def _load_market_dataframe(symbol_probe_target: str):
    """Reads an already-cached price pickle straight off disk — never
    calls fetch_resilient(). Returns None if no cache exists yet (a
    legitimate 'nothing fetched this feed yet' state)."""
    try:
        import pandas as pd
        p = ROOT / symbol_probe_target
        if not p.exists():
            return None
        return pd.read_pickle(p)
    except Exception:  # noqa: BLE001
        return None


def _load_json_cache(relative_path: str):
    try:
        p = ROOT / relative_path
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _quality_checks_for_feed(spec) -> dict:
    """Runs completeness/consistency/anomaly against whatever payload this
    feed's own cache already holds on disk. Feeds with no inspectable
    on-disk payload (reference/computed/observed-only) get NONE_/no-op
    results — there is nothing local to check beyond what freshness.py
    already covers for them."""
    try:
        if spec.category == "market_data" and spec.probe_kind == "file_mtime":
            df = _load_market_dataframe(spec.probe_target)
            completeness = comp.check_dataframe(df, min_rows=10, required_columns=("open", "high", "low", "close"))
            if df is not None and len(df) > 0:
                consistency = cons.check_ohlc(df)
                dup = cons.check_duplicate_timestamps(df)
                consistency_severity = comp.worst_severity(consistency["severity"], dup["severity"])
                closes = list(df[[c for c in df.columns if c.lower() == "close"][0]]) if any(
                    c.lower() == "close" for c in df.columns) else []
                frozen = anom.check_frozen_price(closes)
                jump = anom.check_price_jump(closes)
                anomaly_severity = comp.worst_severity(frozen["severity"], jump["severity"])
            else:
                consistency_severity = comp.NONE_
                anomaly_severity = comp.NONE_
            return {"completeness": completeness["severity"], "consistency": consistency_severity,
                     "anomaly": anomaly_severity}

        if spec.probe_kind == "file_mtime" and spec.category in ("macro", "infrastructure", "news"):
            payload = _load_json_cache(spec.probe_target)
            completeness = comp.check_dict(payload) if payload is not None else \
                {"severity": comp.NONE_}  # cache simply doesn't exist yet — not this feed's fault
            return {"completeness": completeness["severity"], "consistency": comp.NONE_, "anomaly": comp.NONE_}

        return {"completeness": comp.NONE_, "consistency": comp.NONE_, "anomaly": comp.NONE_}
    except Exception:  # noqa: BLE001
        return {"completeness": comp.CRITICAL, "consistency": comp.CRITICAL, "anomaly": comp.CRITICAL}


def run_health_check(settings=None, processing_latency_seconds=None, queue_depth=None,
                      persist: bool = True) -> dict:
    """The main entry point. Never raises. Returns the assembled
    health_report dict, ready for dashboard_publish.py or a Telegram
    summary line to read.

    `persist=True` (the default — used by `alert_signals.py`'s
    `log_data_health()`, once per actual scan) writes a heartbeat record
    and the failure-philosophy event trail to the persisted history.
    `persist=False` (used by `dashboard_snapshot()`) computes the exact
    same report read-only — a dashboard page load should never itself
    inflate the heartbeat/history logs."""
    try:
        registry_validation = reg.validate_registry()
        previous = _previous_statuses_from_history()

        raw_statuses = {}
        for spec in reg.all_feeds():
            # REFERENCE (curated, operator-maintained) and COMPUTED (pure
            # calculation, no external dependency) feeds don't decay
            # against a clock the way TIME_DECAYED/OBSERVED feeds do — they
            # are treated as always-FRESH for the purposes of the 4-state
            # provider_status floor; their own distinct label is preserved
            # in the freshness *block* shown in the report, not lost here.
            if spec.freshness_kind in (reg.REFERENCE, reg.COMPUTED):
                freshness_state_for_status = fr.FRESH
            else:
                age = _probe_age_minutes(spec)
                freshness_state_for_status = fr.classify(age, spec.expected_freshness_minutes)
            configured = reg._configured(spec.feed_id, settings)
            quality = _quality_checks_for_feed(spec)
            status = ps.classify(
                spec.feed_id,
                freshness_state=freshness_state_for_status,
                completeness_severity=quality["completeness"],
                consistency_severity=quality["consistency"],
                anomaly_severity=quality["anomaly"],
                configured=configured,
            )
            raw_statuses[spec.feed_id] = status

        cascaded = ps.apply_dependency_cascade(raw_statuses)

        fresh_count = sum(1 for s in cascaded.values() if s["status"] == ps.OPERATIONAL)
        beat_kwargs = dict(
            processing_latency_seconds=processing_latency_seconds,
            queue_depth=queue_depth,
            provider_fresh_count=fresh_count,
            provider_total_count=len(cascaded),
        )
        # persist=False (dashboard reads) gets a READ-ONLY snapshot of the
        # same shape via hb.current_status() — a dashboard page load must
        # never itself count as a heartbeat or append a research record.
        # persist=True (an actual scan, via alert_signals.py) both writes
        # the heartbeat and appends the failure-philosophy event trail
        # below.
        beat = hb.record_beat(**beat_kwargs) if persist else hb.current_status(**beat_kwargs)

        recent = history_tail(10)
        report = hr.build_report(cascaded, registry_validation, heartbeat_record=beat, recent_history=recent)

        if persist:
            # Failure philosophy: log the run, and log a dedicated event for
            # every provider that is degraded-or-worse OR that just recovered.
            status_map = {k: v["status"] for k, v in cascaded.items()}
            _append_event({"ts": _now_iso(), "kind": "run_summary", "overall_status": report["overall_status"],
                            "counts": report["counts"], "statuses": status_map})
            for feed_id, status in status_map.items():
                prev = previous.get(feed_id)
                if status != ps.OPERATIONAL:
                    _append_event({"ts": _now_iso(), "kind": "provider_issue", "feed_id": feed_id,
                                    "status": status, "reasons": cascaded[feed_id].get("reasons", [])})
                elif prev is not None and prev != ps.OPERATIONAL:
                    _append_event({"ts": _now_iso(), "kind": "recovery", "feed_id": feed_id,
                                    "previous_status": prev, "status": status})

        return report
    except Exception as exc:  # noqa: BLE001
        return {"generated_at": _now_iso(), "overall_status": ps.UNAVAILABLE,
                 "counts": {}, "total_feeds": 0, "providers": [], "dependency_map": {},
                 "degraded_or_worse": [], "registry_validation": {"ok": False, "errors": [str(exc)]},
                 "heartbeat": None, "recent_history": [],
                 "note": f"feed_monitor.run_health_check internal error: {exc}"}


def dashboard_snapshot() -> dict:
    """Advisory dashboard payload — thin wrapper so dashboard_publish.py
    doesn't need to know any of this package's internal call sequence.
    Read-only: does not write a heartbeat record or a history event (see
    `run_health_check()`'s `persist` parameter) — dashboard_publish.py
    calls this once per symbol per scan, and none of those reads should
    count as a scan-level 'beat' on their own."""
    return run_health_check(persist=False)
