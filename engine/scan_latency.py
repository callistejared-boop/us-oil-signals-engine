"""Scan-cycle latency timer (V2.2 Priority 1 Item 2).

A scan is not a single linear pipeline: most stages (market fetch, regime,
confluence, portfolio risk, confidence, memory, explainability) run once
PER SYMBOL inside alert_signals.py::main()'s loop, and a few (macro,
execution simulation, paper broker submission) only run when a setup
actually fires (Stage-2 entry). So "how long did stage X take this scan"
has to mean "cumulative elapsed time across every call to stage X during
this scan", not a single start/end pair.

ScanTimer.stage(name) is a context manager that sums elapsed time across
every `with timer.stage(name):` block hit during one scan, however many
times that happens (0, 1, or once per symbol). One ScanTimer instance is
constructed per call to main() and handed to engine/scan_latency_history.py
at the end of the scan to persist.

Never raises: a timing bug must never disrupt trading logic, same
fail-safe posture as every other advisory-only module in this codebase
(ledger.py, regime_history.py, etc.) - the timer's own bookkeeping is
wrapped in try/except, but the code inside a `with timer.stage(...):`
block still raises/propagates normally, exactly like a bare `with` would.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

VERSION = "1.0.0"


class ScanTimer:
    def __init__(self):
        self._t0 = time.monotonic()
        self._stage_ms: dict = {}
        self._stage_calls: dict = {}

    @contextmanager
    def stage(self, name: str):
        t0 = time.monotonic()
        try:
            yield
        finally:
            try:
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                self._stage_ms[name] = self._stage_ms.get(name, 0.0) + elapsed_ms
                self._stage_calls[name] = self._stage_calls.get(name, 0) + 1
            except Exception:  # noqa: BLE001
                pass

    def total_ms(self) -> float:
        try:
            return (time.monotonic() - self._t0) * 1000.0
        except Exception:  # noqa: BLE001
            return 0.0

    def snapshot(self) -> dict:
        """Cumulative ms per stage recorded so far this scan, rounded for
        readability. A stage that never fired this scan (e.g. macro/
        execution/paper_broker on a scan with no entries) is simply
        absent, not zero."""
        return {k: round(v, 3) for k, v in self._stage_ms.items()}

    def call_counts(self) -> dict:
        return dict(self._stage_calls)
