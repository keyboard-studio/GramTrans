"""Unit tests for the hang-labeling close watcher (_close_project_watchdog).

Regression guard for the coverage_report.py freeze: when the target is
co-held by another process, FLExProject.CloseProject() blocks INDEFINITELY.

History note: the first version of this watchdog ran CloseProject on a
daemon thread and raised after a deadline. That violated LCM thread
affinity -- event handlers raised during Save/Close marshal to the OPENING
thread via ThreadHelper.Invoke, which a pump-less Python host never
services from another thread -- so the watchdog itself could deadlock LCM
(observed live: a Save with gathered changes wedged on the daemon thread).
The current design runs the call ON THE CALLER'S THREAD and uses a passive
watcher that only LABELS the hang (log + console) after the deadline; it
cannot abort the call, but a wedged run now names its own cause instead of
freezing silently. These tests exercise the helper with host-free fakes
(no flexicon / pythonnet).
"""
from __future__ import annotations

import logging
import time

import pytest

from gramtrans.Lib.api import _close_project_watchdog, _watched_call


class _FastClose:
    def __init__(self) -> None:
        self.closed = False

    def CloseProject(self):  # noqa: N802
        self.closed = True


class _SlowClose:
    """CloseProject outlives the watcher deadline, then completes -- models a
    close that is slow (or briefly contended) but not permanently wedged. A
    PERMANENT hang cannot be unit-tested with the on-thread design (the test
    itself would hang); the watcher's warning firing before completion is the
    observable contract."""

    def __init__(self, duration_s: float) -> None:
        self._duration_s = duration_s
        self.closed = False

    def CloseProject(self):  # noqa: N802
        time.sleep(self._duration_s)
        self.closed = True


class _RaisingClose:
    def CloseProject(self):  # noqa: N802
        raise ValueError("backend refused the save")


def test_watchdog_returns_when_close_is_fast(caplog):
    """A healthy close completes, the watchdog returns, no warning fires."""
    proj = _FastClose()
    with caplog.at_level(logging.WARNING, logger="gramtrans.Lib.api"):
        _close_project_watchdog(proj, 5.0, "fast close")
    assert proj.closed is True
    assert not caplog.records


def test_watchdog_runs_close_on_the_caller_thread():
    """LCM thread affinity: the close must execute on the calling thread."""
    import threading

    seen = {}

    class _ThreadRecorder:
        def CloseProject(self):  # noqa: N802
            seen["thread"] = threading.current_thread()

    _close_project_watchdog(_ThreadRecorder(), 5.0, "thread check")
    assert seen["thread"] is threading.main_thread()


def test_watchdog_labels_a_hang_past_the_deadline(caplog):
    """A close that outlives the deadline gets a WARNING naming the handle,
    the likely cause, and the env knob -- while the call keeps running on
    the caller's thread and still completes."""
    proj = _SlowClose(duration_s=0.5)
    with caplog.at_level(logging.WARNING, logger="gramtrans.Lib.api"):
        _close_project_watchdog(proj, 0.1, "custom-field schema write")
    assert proj.closed is True  # the call was not aborted
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "custom-field schema write" in msg
    assert "another process" in msg
    assert "GRAMTRANS_SCHEMA_CLOSE_TIMEOUT" in msg


def test_watchdog_reraises_close_exception():
    """An exception inside CloseProject propagates unchanged."""
    with pytest.raises(ValueError, match="backend refused the save"):
        _close_project_watchdog(_RaisingClose(), 5.0, "raising close")


# ---------------------------------------------------------------------------
# _watched_call (the generic helper underneath)
# ---------------------------------------------------------------------------

def test_watched_call_returns_fn_result():
    assert _watched_call(lambda: 42, 5.0, "returning fn") == 42


def test_watched_call_no_warning_when_fast(caplog):
    with caplog.at_level(logging.WARNING, logger="gramtrans.Lib.api"):
        _watched_call(lambda: None, 5.0, "fast fn")
    assert not caplog.records


def test_watched_call_warns_once_past_deadline(caplog):
    with caplog.at_level(logging.WARNING, logger="gramtrans.Lib.api"):
        _watched_call(lambda: time.sleep(0.5), 0.1, "slow fn")
    warnings = [r for r in caplog.records if "slow fn" in r.getMessage()]
    assert len(warnings) == 1
    assert "has not completed after" in warnings[0].getMessage()
