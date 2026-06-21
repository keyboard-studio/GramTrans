"""Phase 3b US2 detect-and-skip unit tests for custom_fields callbacks.

Schema creation is blocked at the flexlibs2 layer (see us2-blocker-memo.md).
US2 ships as detect-and-report: enumerate source's custom fields, compare
to target's, emit Skip(NEEDS_MANUAL) for absent fields directing user to
pre-create in FLEx UI. plan_action emits Skip directly (per lex-qc P1
invariant); execute_action is a registered no-op for dispatch hygiene.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib import categories
from gramtrans.Lib.models import (
    GrammarCategory,
    PlannedAction,
    RunContext,
    Selection,
    Skip,
    SkipReason,
    WSMapping,
)


# ============================================================================
# Fakes
# ============================================================================

class _FakeCFOps:
    """Mimics flexlibs2 CustomFieldOperations read surface."""

    def __init__(self, fields=None):
        # fields: dict[owner_class -> list[(field_id, name)]]
        self._fields = fields or {}

    def GetAllFields(self, owner_class):
        return list(self._fields.get(owner_class, []))

    def FindField(self, owner_class, name):
        for fid, label in self._fields.get(owner_class, []):
            if label == name:
                return fid
        return 0


class _FakeProject:
    def __init__(self, custom_fields=None):
        self.CustomFields = _FakeCFOps(custom_fields)


def _ctx(src, tgt) -> RunContext:
    return RunContext(
        source_handle=src, source_project_name="Src", source_project_path="/s",
        target_handle=tgt, target_project_name="Tgt", target_project_path="/t",
        run_id="GT-3B-US2", started_at="2026-06-21T02:40:00",
    )


WSM = WSMapping(entries=())
SEL = Selection(categories={})


# ============================================================================
# enumerate_source
# ============================================================================

def test_enumerate_walks_supported_owner_classes() -> None:
    src = _FakeProject(custom_fields={
        "LexEntry": [(5002, "Noun class"), (5003, "Loanword origin")],
        "LexSense": [(5004, "Tone melody")],
    })
    tgt = _FakeProject()
    records = categories.custom_fields_enumerate_source(_ctx(src, tgt), SEL)
    names = {(r.owner_class, r.name) for r in records}
    assert names == {
        ("LexEntry", "Noun class"),
        ("LexEntry", "Loanword origin"),
        ("LexSense", "Tone melody"),
    }


def test_enumerate_returns_empty_when_no_customfields_accessor() -> None:
    src = object()  # no CustomFields attribute
    tgt = _FakeProject()
    assert categories.custom_fields_enumerate_source(_ctx(src, tgt), SEL) == []


def test_enumerate_handles_missing_owner_class_gracefully() -> None:
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "X")]})  # only one class
    tgt = _FakeProject()
    records = categories.custom_fields_enumerate_source(_ctx(src, tgt), SEL)
    # The other 3 supported classes should just be empty, not raise.
    assert len(records) == 1
    assert records[0].name == "X"


def test_custom_field_record_synthetic_guid() -> None:
    rec = categories._CustomFieldRecord("LexSense", "Tone melody", 5004)
    assert rec.guid == "cf:LexSense:Tone melody"
    assert rec.Guid == rec.guid  # ICmObject-compat alias
    assert rec.CatalogSourceId == ""  # never GOLD


# ============================================================================
# plan_action -- detect-and-skip
# ============================================================================

def test_plan_action_emits_needs_manual_when_target_absent() -> None:
    rec = categories._CustomFieldRecord("LexEntry", "Noun class")
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "Noun class")]})
    tgt = _FakeProject(custom_fields={})  # target has nothing
    result = categories.custom_fields_plan_action(rec, _ctx(src, tgt), WSM)
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.NEEDS_MANUAL
    assert result.category == GrammarCategory.CUSTOM_FIELDS
    assert "Pre-create" in result.detail
    assert "case-sensitive" in result.detail
    assert "Noun class" in result.detail


def test_plan_action_emits_already_present_when_target_has_field() -> None:
    """Match by (class_id, name) -> ALREADY_PRESENT_BY_IDENTITY (distinct
    from ALREADY_PRESENT_BY_GUID because custom fields have no LCM Guid)."""
    rec = categories._CustomFieldRecord("LexEntry", "Noun class")
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "Noun class")]})
    tgt = _FakeProject(custom_fields={"LexEntry": [(7001, "Noun class")]})  # same name
    result = categories.custom_fields_plan_action(rec, _ctx(src, tgt), WSM)
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_IDENTITY
    assert "already present" in result.detail
    assert "(class_id, name) identity" in result.detail


def test_plan_action_handles_target_without_customfields_accessor() -> None:
    rec = categories._CustomFieldRecord("LexEntry", "Foo")
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "Foo")]})
    tgt = object()  # no CustomFields
    result = categories.custom_fields_plan_action(rec, _ctx(src, tgt), WSM)
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.NEEDS_MANUAL  # treated as absent


def test_plan_action_never_emits_planned_action() -> None:
    """lex-qc P1 invariant: plan_action MUST emit Skip directly, not
    a PlannedAction that re-skips at execute time. Both branches
    (target-absent and target-present) MUST honor this."""
    rec = categories._CustomFieldRecord("LexEntry", "Foo")
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "Foo")]})

    # Branch 1: target ABSENT -> NEEDS_MANUAL
    tgt_absent = _FakeProject()
    result_absent = categories.custom_fields_plan_action(rec, _ctx(src, tgt_absent), WSM)
    assert not isinstance(result_absent, PlannedAction)
    assert isinstance(result_absent, Skip)
    assert result_absent.reason == SkipReason.NEEDS_MANUAL

    # Branch 2: target PRESENT -> ALREADY_PRESENT_BY_IDENTITY
    tgt_present = _FakeProject(custom_fields={"LexEntry": [(7001, "Foo")]})
    result_present = categories.custom_fields_plan_action(rec, _ctx(src, tgt_present), WSM)
    assert not isinstance(result_present, PlannedAction)
    assert isinstance(result_present, Skip)
    assert result_present.reason == SkipReason.ALREADY_PRESENT_BY_IDENTITY


def test_plan_action_findfield_exception_degrades_to_needs_manual() -> None:
    """lex-qc P2 coverage: when target's FindField raises, treat as absent
    (silent-degrade-to-NEEDS_MANUAL path at categories.py)."""
    class _RaisingCFOps(_FakeCFOps):
        def FindField(self, owner_class, name):
            raise RuntimeError("simulated MDC accessor failure")

    rec = categories._CustomFieldRecord("LexEntry", "Foo")
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "Foo")]})
    tgt = _FakeProject()
    tgt.CustomFields = _RaisingCFOps({})  # swap in raising ops
    result = categories.custom_fields_plan_action(rec, _ctx(src, tgt), WSM)
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.NEEDS_MANUAL


# ============================================================================
# dependencies + required_writing_systems
# ============================================================================

def test_dependencies_is_leaf() -> None:
    rec = categories._CustomFieldRecord("LexEntry", "X")
    assert categories.custom_fields_dependencies(rec) == ()


def test_required_writing_systems_returns_empty() -> None:
    rec = categories._CustomFieldRecord("LexEntry", "X")
    assert tuple(categories.custom_fields_required_writing_systems(rec)) == ()


# ============================================================================
# execute_action -- registered no-op
# ============================================================================

def test_execute_action_is_a_noop() -> None:
    """plan_action emits Skip so executor never reaches this path,
    but the stub must exist (registered) for dispatch hygiene."""
    rec = categories._CustomFieldRecord("LexEntry", "X")
    action = PlannedAction(
        category=GrammarCategory.CUSTOM_FIELDS,
        source_guid=rec.guid,
        intended_target_guid=rec.guid,
        summary="should-never-fire",
    )
    src = _FakeProject()
    tgt = _FakeProject()
    # If this ever ran live it would still complete without raising.
    result = categories.custom_fields_execute_action(
        action, _ctx(src, tgt), WSM, tag=None
    )
    assert result is None


# ============================================================================
# Registry sanity
# ============================================================================

def test_registry_bundle_complete() -> None:
    bundle = categories.for_category(GrammarCategory.CUSTOM_FIELDS)
    assert bundle["enumerate_source"] is categories.custom_fields_enumerate_source
    assert bundle["plan_action"] is categories.custom_fields_plan_action
    assert bundle["execute_action"] is categories.custom_fields_execute_action
    assert bundle["dependencies"] is categories.custom_fields_dependencies
    assert bundle["required_writing_systems"] is categories.custom_fields_required_writing_systems
