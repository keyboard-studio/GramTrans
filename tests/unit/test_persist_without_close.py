"""Unit tests for _persist_without_close -- the FLEx-parity persist checkpoint.

flexicon's non-undoable open holds an ambient NonUndoableTask from
OpenProject onward, and LCM's UnitOfWorkService.Save() throws "Commit at
wrong place" (and rolls back) while any task is open. So persisting WITHOUT
closing must be the exact triplet CloseProject() runs minus the
deadlock-prone Dispose():

    MainCacheAccessor.EndNonUndoableTask()
    IUndoStackManager.Save()          (on the CALLER'S thread -- LCM affinity)
    MainCacheAccessor.BeginNonUndoableTask()

These tests exercise the helper with host-free fakes: a fake ``SIL.LCModel``
module is injected so the lazy ``from SIL.LCModel import IUndoStackManager``
resolves without pythonnet.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
import types

import pytest

from gramtrans.Lib import api as api_mod
from gramtrans.Lib.api import _persist_without_close


class _IUndoStackManager:
    """Sentinel interface class; ObjectRepository is keyed on it."""


@pytest.fixture()
def fake_sil(monkeypatch):
    mod = types.ModuleType("SIL.LCModel")
    mod.IUndoStackManager = _IUndoStackManager
    sil_pkg = types.ModuleType("SIL")
    sil_pkg.LCModel = mod
    monkeypatch.setitem(sys.modules, "SIL", sil_pkg)
    monkeypatch.setitem(sys.modules, "SIL.LCModel", mod)


class _FakeProj:
    """FLExProject stand-in recording the End/Save/Begin call order."""

    def __init__(self, save_behavior="ok", save_duration_s=0.0):
        self.calls: list = []
        self.save_thread = None
        self._save_behavior = save_behavior
        self._save_duration_s = save_duration_s

        proj = self

        class _Mca:
            def EndNonUndoableTask(self):  # noqa: N802
                proj.calls.append("End")

            def BeginNonUndoableTask(self):  # noqa: N802
                proj.calls.append("Begin")

        class _Usm:
            def Save(self):  # noqa: N802
                proj.calls.append("Save")
                proj.save_thread = threading.current_thread()
                if proj._save_duration_s:
                    time.sleep(proj._save_duration_s)
                if proj._save_behavior == "raise":
                    raise RuntimeError("Commit at wrong place.")

        self.project = types.SimpleNamespace(MainCacheAccessor=_Mca())
        self._usm = _Usm()

    def ObjectRepository(self, repository):  # noqa: N802
        assert repository is _IUndoStackManager
        return self._usm


def test_persist_runs_end_save_begin_in_order(fake_sil):
    proj = _FakeProj()
    _persist_without_close(proj, "custom-field schema write")
    assert proj.calls == ["End", "Save", "Begin"]


def test_persist_runs_save_on_the_caller_thread(fake_sil):
    """LCM thread affinity: Save must NOT be shipped to a watchdog thread.
    (Regression: an off-thread Save deadlocked live -- event handlers marshal
    to the opening thread via ThreadHelper.Invoke, which a pump-less host
    never services from another thread.)"""
    proj = _FakeProj()
    _persist_without_close(proj, "custom-field schema write")
    assert proj.save_thread is threading.main_thread()


def test_ambient_task_restored_even_when_save_raises(fake_sil):
    """Begin must run even on Save failure so the handle stays usable and
    CloseProject()'s EndNonUndoableTask still has a task to end."""
    proj = _FakeProj(save_behavior="raise")
    with pytest.raises(RuntimeError, match="Commit at wrong place"):
        _persist_without_close(proj, "custom-field schema write")
    assert proj.calls == ["End", "Save", "Begin"]


def test_slow_save_gets_a_labeled_warning_and_still_completes(fake_sil, caplog, monkeypatch):
    """A Save that outlives the deadline is LABELED (log warning naming the
    operation, the likely co-holder cause, and the env knob) while the call
    keeps running on the caller's thread to completion."""
    monkeypatch.setattr(api_mod, "_SCHEMA_CLOSE_TIMEOUT_S", 0.1)
    proj = _FakeProj(save_duration_s=0.5)
    with caplog.at_level(logging.WARNING, logger="gramtrans.Lib.api"):
        _persist_without_close(proj, "custom-field schema write")
    assert proj.calls == ["End", "Save", "Begin"]
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "custom-field schema write" in msg
    assert "has not completed after" in msg
    assert "GRAMTRANS_SCHEMA_CLOSE_TIMEOUT" in msg
