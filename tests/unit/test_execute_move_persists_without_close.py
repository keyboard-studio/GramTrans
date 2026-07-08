"""Tests for the reworked custom-field create path in execute_move.

The old PATH-CLOSE-REBIND dance (close Phase-1 handle -> fresh handle ->
AddCustomField -> CloseProject-to-persist -> reopen -> rebind) deadlocked
whenever anything co-held the target, because SharedXMLBackendProvider's
dispose takes the commit-log mutex with no timeout. The rework is FLEx
parity: AddCustomField mutates the in-memory metadata cache on the caller's
OWN handle, and persistence happens via _persist_without_close (the
End -> Save -> Begin checkpoint) -- no close, no reopen, no handle rebind.

These tests drive execute_move with host-free fakes (no SIL.LCModel /
pythonnet) and assert the new invariants:

1. transfer.execute receives the ORIGINAL context.target_handle (no handle
   divergence -- the wizard cleanup closes the object that got the writes).
2. The schema pre-pass runs on that same handle BEFORE execute.
3. A post-transfer checkpoint persists the value writes AFTER execute,
   even when execute raises (mirroring the old close-in-finally semantics).
4. execute_move never closes the target handle and never opens a fresh one;
   the caller owns the handle lifecycle.
"""
from __future__ import annotations

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


class _FakeTargetHandle:
    """Records CloseProject so the test can assert execute_move never calls it."""

    def __init__(self) -> None:
        self.close_count = 0

    def CloseProject(self):  # noqa: N802
        self.close_count += 1


def _make_context() -> RunContext:
    return RunContext(
        source_handle=object(),
        source_project_name="S",
        source_project_path="/s",
        target_handle=_FakeTargetHandle(),
        target_project_name="T",
        target_project_path="/t",
        run_id="GT-20260706-120000",
        started_at="2026-07-06T12:00:00",
    )


def _make_plan(context: RunContext, with_create: bool = True) -> RunPlan:
    actions = ()
    if with_create:
        actions = (
            CreateDefinitionAction(
                category=GrammarCategory.CUSTOM_FIELDS,
                source_guid="cf:LexEntry:MyField",
                owner_class="LexEntry",
                field_name="MyField",
                field_type=13,
                list_root_guid="",
                summary="new custom field MyField on LexEntry",
            ),
        )
    return RunPlan(
        context=context,
        selection=Selection(),
        ws_mapping=WSMapping(entries=()),
        actions=actions,
    )


@pytest.fixture()
def recorder(monkeypatch):
    """Stub the host-touching seams and record the call sequence."""
    calls = []

    def _fake_ensure(proj, actions):
        calls.append(("ensure", proj, tuple(actions)))
        return [a.field_name for a in actions]

    def _fake_checkpoint(proj, what):
        calls.append(("checkpoint", proj, what))

    def _fake_execute(plan, source, target, sink, tag):
        calls.append(("execute", target))
        return RunReport(context=plan.context, mode=RunMode.MOVE)

    monkeypatch.setattr(api_mod, "_ensure_custom_fields", _fake_ensure)
    monkeypatch.setattr(api_mod, "_persist_without_close", _fake_checkpoint)
    monkeypatch.setattr(transfer_mod, "execute", _fake_execute)
    return calls


def test_create_path_uses_one_handle_in_order(recorder):
    """Schema pre-pass -> execute -> value checkpoint, all on the ORIGINAL
    target handle; the handle is never closed by execute_move."""
    context = _make_context()
    plan = _make_plan(context)

    report = execute_move(context, plan)

    assert isinstance(report, RunReport)
    assert [c[0] for c in recorder] == ["ensure", "execute", "checkpoint"]

    original = context.target_handle
    assert recorder[0][1] is original, "schema pre-pass ran on a different handle"
    assert recorder[1][1] is original, "execute received a different handle"
    assert recorder[2][1] is original, "value checkpoint ran on a different handle"
    assert original.close_count == 0, (
        "execute_move must not close the caller's handle (caller owns lifecycle)"
    )


def test_value_checkpoint_runs_even_when_execute_raises(recorder, monkeypatch):
    """Mirrors the old close-in-finally semantics: a partial write pass is
    still persisted, and execute's exception propagates."""
    def _boom(plan, source, target, sink, tag):
        recorder.append(("execute", target))
        raise RuntimeError("write pass blew up")

    monkeypatch.setattr(transfer_mod, "execute", _boom)

    context = _make_context()
    plan = _make_plan(context)

    with pytest.raises(RuntimeError, match="write pass blew up"):
        execute_move(context, plan)

    assert [c[0] for c in recorder] == ["ensure", "execute", "checkpoint"]


def test_checkpoint_failure_does_not_mask_execute_result(recorder, monkeypatch):
    """A wedged/failed post-transfer checkpoint is warning-grade: the
    RunReport from execute must still be returned."""
    def _bad_checkpoint(proj, what):
        recorder.append(("checkpoint", proj, what))
        raise RuntimeError("Save() for post-transfer value writes did not complete")

    monkeypatch.setattr(api_mod, "_persist_without_close", _bad_checkpoint)

    context = _make_context()
    plan = _make_plan(context)

    report = execute_move(context, plan)  # must NOT raise

    assert isinstance(report, RunReport)
    assert [c[0] for c in recorder] == ["ensure", "execute", "checkpoint"]


def test_non_create_path_skips_schema_and_checkpoint(recorder):
    """Plans without CreateDefinitionActions keep the plain execute path:
    no schema pre-pass, no checkpoint (the caller's CloseProject persists)."""
    context = _make_context()
    plan = _make_plan(context, with_create=False)

    report = execute_move(context, plan)

    assert isinstance(report, RunReport)
    assert [c[0] for c in recorder] == ["execute"]
    assert context.target_handle.close_count == 0
