"""Regression test for the PATH-CLOSE-REBIND write-loss bug in execute_move.

Bug (T017 branch): when a plan contains CreateDefinitionActions for new custom
fields, execute_move closes the Phase-1 preview handle, calls
_ensure_custom_fields, opens a FRESH write-enabled FLExProject, rebinds the
context/plan to it, and runs transfer.execute writing ALL grammar objects into
that fresh handle. FLEx only persists writes when the handle is closed
(CloseProject -> EndNonUndoableTask + usm.Save). Nothing closed the fresh
handle -- the wizard's cleanup (gramtrans.py _run_gui) closes the ORIGINAL,
already-disposed handle -- so every object write was discarded on exit.

This test drives execute_move through the create_actions rebind branch with
host-free fakes (no SIL.LCModel / pythonnet) and asserts that the fresh target
handle that received the object writes had CloseProject() called on it, i.e.
the writes are flushed/saved.
"""
from __future__ import annotations

import sys
import types

import pytest

from gramtrans.Lib.api import execute_move
from gramtrans.Lib import api as api_mod
from gramtrans.Lib import transfer as transfer_mod
from gramtrans.Lib.models import (
    CreateDefinitionAction,
    GrammarCategory,
    RunContext,
    RunMode,
    RunPlan,
    RunReport,
    Selection,
    WSMapping,
)


class _FakeFLExProject:
    """Records OpenProject / CloseProject so the test can assert the fresh
    handle was closed (== writes flushed)."""

    #: every fresh handle execute_move opens is appended here.
    instances: list = []

    def __init__(self) -> None:
        self.opened = False
        self.closed = False
        self.close_count = 0
        _FakeFLExProject.instances.append(self)

    def OpenProject(self, projectName=None, writeEnabled=False):  # noqa: N802,N803
        self.opened = True
        self.write_enabled = writeEnabled

    def CloseProject(self):  # noqa: N802
        self.closed = True
        self.close_count += 1


def _make_context() -> RunContext:
    return RunContext(
        source_handle=object(),
        source_project_name="S",
        source_project_path="/s",
        # Phase-1 preview handle: also a fake so its CloseProject is a no-op.
        target_handle=_FakeFLExProject(),
        target_project_name="T",
        target_project_path="/t",
        run_id="GT-20260706-120000",
        started_at="2026-07-06T12:00:00",
    )


def _make_plan(context: RunContext) -> RunPlan:
    create = CreateDefinitionAction(
        category=GrammarCategory.CUSTOM_FIELDS,
        source_guid="cf:LexEntry:MyField",
        owner_class="LexEntry",
        field_name="MyField",
        field_type=13,
        list_root_guid="",
        summary="new custom field MyField on LexEntry",
    )
    return RunPlan(
        context=context,
        selection=Selection(),
        ws_mapping=WSMapping(entries=()),
        actions=(create,),
    )


def test_execute_move_closes_fresh_target_after_custom_field_rebind(monkeypatch):
    """After an Execute Move whose plan adds custom fields, the FRESH target
    handle (the one that received the object writes) must have CloseProject()
    called on it -- otherwise FLEx discards every write on exit."""
    _FakeFLExProject.instances = []

    # Inject a fake `flexicon` module so the lazy `from flexicon import
    # FLExProject` inside the rebind branch resolves to our recorder.
    fake_flexicon = types.ModuleType("flexicon")
    fake_flexicon.FLExProject = _FakeFLExProject
    monkeypatch.setitem(sys.modules, "flexicon", fake_flexicon)

    # The schema pre-pass talks to a live host; stub it out.
    monkeypatch.setattr(api_mod, "_ensure_custom_fields", lambda name, actions: [])

    # Capture the target handle transfer.execute actually receives, and return
    # a minimal valid RunReport instead of running the real executor.
    seen = {}

    def _fake_execute(plan, source, target, sink, tag):
        seen["target"] = target
        return RunReport(context=plan.context, mode=RunMode.MOVE)

    monkeypatch.setattr(transfer_mod, "execute", _fake_execute)

    context = _make_context()
    plan = _make_plan(context)

    report = execute_move(context, plan)

    assert isinstance(report, RunReport)

    # A fresh handle was opened for the write pass.
    fresh = seen["target"]
    assert isinstance(fresh, _FakeFLExProject)
    assert fresh.opened is True
    assert fresh.write_enabled is True

    # THE REGRESSION ASSERTION: the fresh handle that received the writes was
    # closed, so FLEx flushes/persists them. Before the fix this was False.
    assert fresh.closed is True, (
        "fresh target handle was never CloseProject()'d after execute -- "
        "every object write would be discarded on exit"
    )


def test_execute_move_closes_fresh_target_even_when_execute_raises(monkeypatch):
    """The fresh handle must be closed even if transfer.execute raises, so a
    partial write pass is still persisted / the handle is not leaked."""
    _FakeFLExProject.instances = []

    fake_flexicon = types.ModuleType("flexicon")
    fake_flexicon.FLExProject = _FakeFLExProject
    monkeypatch.setitem(sys.modules, "flexicon", fake_flexicon)
    monkeypatch.setattr(api_mod, "_ensure_custom_fields", lambda name, actions: [])

    def _boom(plan, source, target, sink, tag):
        raise RuntimeError("write pass blew up")

    monkeypatch.setattr(transfer_mod, "execute", _boom)

    context = _make_context()
    plan = _make_plan(context)

    with pytest.raises(RuntimeError, match="write pass blew up"):
        execute_move(context, plan)

    # The fresh handle (last one opened) must have been closed by the finally.
    fresh = _FakeFLExProject.instances[-1]
    assert fresh.opened is True
    assert fresh.closed is True
