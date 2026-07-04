"""Phase 3b US2 detect-and-skip unit tests for custom_fields callbacks.

Schema creation is blocked at the flexicon layer (see us2-blocker-memo.md).
US2 ships as detect-and-report: enumerate source's custom fields, compare
to target's, emit Skip(NEEDS_MANUAL) for absent fields directing user to
pre-create in FLEx UI. plan_action emits Skip directly (per lex-qc P1
invariant); execute_action is a registered no-op for dispatch hygiene.

T005 (spec 016, Phase 2) extends this file with TDD-red tests for:
  - _CustomFieldRecord carrying field_type:int and list_root_guid
  - NEW vs IN_TARGET classification by (owner_class, name) match
  - type-difference on a (class,name) match -> IN_TARGET + type_diff_note,
    NOT IDENTITY_COLLISION
  - custom_field_type_label renderer

These tests target categories.py functions NOT YET IMPLEMENTED (T006/T007).
They are expected to FAIL (red) until T006/T007 land.
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
from _fakes_custom_fields import (
    make_source,
    make_target,
    FakeSourceHandle,
    FakeTargetHandle,
)


# ============================================================================
# Fakes
# ============================================================================

class _FakeCFOps:
    """Mimics flexicon CustomFieldOperations read surface."""

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


# ============================================================================
# T005 (spec 016, Phase 2) -- TDD-red until T006/T007 land
#
# These tests target:
#   - categories._CustomFieldRecord  (extended with field_type + list_root_guid)
#   - categories.custom_field_type_label(field_type)          [T006]
#   - categories.classify_custom_field(record, target)         [T007]
#
# ALL tests in this section are expected to FAIL until T006/T007 are
# implemented.  Do not change them to pass by faking the assertions.
# ============================================================================

# CellarPropertyType constants (research.md section 1)
CPT_BOOLEAN       = 1
CPT_INTEGER       = 2
CPT_GENDATE       = 8
CPT_STRING        = 13   # "Text"
CPT_MULTISTRING   = 14
CPT_MULTIUNICODE  = 16
CPT_OWNINGATOMIC  = 23
CPT_REFATOMIC     = 24   # "List item"
CPT_REFCOLLECTION = 26   # "List item"


class TestCustomFieldRecordExtended:
    """_CustomFieldRecord must carry field_type:int and list_root_guid.

    RED until T006 extends _CustomFieldRecord.__slots__ / __init__.
    """

    def test_record_carries_field_type(self) -> None:
        rec = categories._CustomFieldRecord("LexEntry", "Noun class", 5100,
                                            field_type=CPT_STRING)
        assert rec.field_type == CPT_STRING

    def test_record_carries_list_root_guid(self) -> None:
        guid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        rec = categories._CustomFieldRecord("LexSense", "Tone melody", 5101,
                                            field_type=CPT_REFATOMIC,
                                            list_root_guid=guid)
        assert rec.list_root_guid == guid

    def test_record_list_root_defaults_to_empty(self) -> None:
        rec = categories._CustomFieldRecord("MoForm", "Variant flag", 5102,
                                            field_type=CPT_BOOLEAN)
        assert rec.list_root_guid == ""

    def test_record_field_type_defaults_to_zero(self) -> None:
        # Backward compat: old call sites (Phase-3b) pass no field_type.
        rec = categories._CustomFieldRecord("LexEntry", "Old field", 5099)
        assert rec.field_type == 0

    def test_record_synthetic_guid_unchanged(self) -> None:
        rec = categories._CustomFieldRecord("LexEntry", "Noun class", 5100,
                                            field_type=CPT_STRING)
        assert rec.guid == "cf:LexEntry:Noun class"
        assert rec.Guid == rec.guid


class TestCustomFieldTypeLabel:
    """custom_field_type_label(int) -> str.

    RED until T006 adds the helper to categories.py.
    """

    @pytest.mark.parametrize("cpt,expected", [
        (CPT_STRING,        "Text"),
        (CPT_MULTIUNICODE,  "Multi-Unicode"),
        (CPT_MULTISTRING,   "Multi-string"),
        (CPT_INTEGER,       "Integer"),
        (CPT_GENDATE,       "Date"),
        (CPT_BOOLEAN,       "Boolean"),
        (CPT_OWNINGATOMIC,  "Item (owned)"),
        (CPT_REFATOMIC,     "List item"),
        (CPT_REFCOLLECTION, "List item"),
    ])
    def test_known_types(self, cpt: int, expected: str) -> None:
        assert categories.custom_field_type_label(cpt) == expected

    def test_unknown_type_returns_fallback(self) -> None:
        label = categories.custom_field_type_label(99)
        assert "99" in label  # fallback contains the raw int


class TestClassifyCustomField:
    """classify_custom_field(record, target) -> (status, type_diff_note|None).

    Status values: "NEW", "IN_TARGET".
    RED until T007 adds the helper to categories.py.
    """

    def test_absent_from_target_is_new(self) -> None:
        src = make_source(entry_fields=[(5100, "Noun class", CPT_STRING, "")])
        tgt = make_target()   # nothing pre-seeded
        rec = categories._CustomFieldRecord("LexEntry", "Noun class", 5100,
                                            field_type=CPT_STRING)
        status, note = categories.classify_custom_field(rec, tgt)
        assert status == "NEW"
        assert note is None

    def test_present_in_target_same_type_is_in_target(self) -> None:
        src = make_source(entry_fields=[(5100, "Noun class", CPT_STRING, "")])
        tgt = make_target(entry_fields=[(7001, "Noun class", CPT_STRING, "")])
        rec = categories._CustomFieldRecord("LexEntry", "Noun class", 5100,
                                            field_type=CPT_STRING)
        status, note = categories.classify_custom_field(rec, tgt)
        assert status == "IN_TARGET"
        assert note is None

    def test_present_in_target_type_diff_is_in_target_with_note(self) -> None:
        """A type difference on a (class,name) match -> IN_TARGET + note.

        Must NOT produce IDENTITY_COLLISION or any blocking result.
        The transfer still proceeds using the target's existing field type.
        """
        src = make_source(sense_fields=[(5101, "Tone melody", CPT_STRING, "")])
        tgt = make_target(sense_fields=[(7002, "Tone melody", CPT_MULTISTRING, "")])
        rec = categories._CustomFieldRecord("LexSense", "Tone melody", 5101,
                                            field_type=CPT_STRING)
        status, note = categories.classify_custom_field(rec, tgt)
        assert status == "IN_TARGET"
        assert note is not None
        assert "type" in note.lower()
        # Must never be called IDENTITY_COLLISION
        assert "identity_collision" not in note.lower()
        assert "IDENTITY_COLLISION" not in note

    def test_type_diff_does_not_produce_identity_collision(self) -> None:
        """FR-008 invariant: no IDENTITY_COLLISION for custom field type diffs."""
        tgt = make_target(entry_fields=[(7001, "Code", CPT_INTEGER, "")])
        rec = categories._CustomFieldRecord("LexEntry", "Code", 5100,
                                            field_type=CPT_STRING)
        status, note = categories.classify_custom_field(rec, tgt)
        # Status must be IN_TARGET, NOT some collision variant.
        assert status == "IN_TARGET"

    def test_match_is_by_owner_class_and_name_only(self) -> None:
        """A field with the same name but different owner class is NEW."""
        tgt = make_target(entry_fields=[(7001, "Dialect note", CPT_STRING, "")])
        # Same name "Dialect note" but on LexSense, not LexEntry.
        rec = categories._CustomFieldRecord("LexSense", "Dialect note", 5102,
                                            field_type=CPT_STRING)
        status, note = categories.classify_custom_field(rec, tgt)
        assert status == "NEW"
        assert note is None

    def test_no_target_accessor_degrades_to_new(self) -> None:
        """When target has no CustomFields attribute, treat all as NEW."""
        tgt = object()  # no CustomFields attribute at all
        rec = categories._CustomFieldRecord("LexEntry", "Foo", 5100,
                                            field_type=CPT_STRING)
        status, note = categories.classify_custom_field(rec, tgt)
        assert status == "NEW"
        assert note is None

    def test_all_four_owner_levels(self) -> None:
        """classify_custom_field works for all four supported owner classes."""
        levels = [
            ("LexEntry",           make_target(entry_fields=[(7001, "F", CPT_STRING, "")])),
            ("LexSense",           make_target(sense_fields=[(7002, "F", CPT_STRING, "")])),
            ("LexExampleSentence", make_target(example_fields=[(7003, "F", CPT_STRING, "")])),
            ("MoForm",             make_target(moform_fields=[(7004, "F", CPT_STRING, "")])),
        ]
        for cls, tgt in levels:
            rec = categories._CustomFieldRecord(cls, "F", 5100, field_type=CPT_STRING)
            status, note = categories.classify_custom_field(rec, tgt)
            assert status == "IN_TARGET", f"Expected IN_TARGET for {cls}"

    def test_empty_level_classifies_as_new(self) -> None:
        """Empty target level -> every source field on that level is NEW."""
        tgt = make_target()  # no fields at any level
        for cls in ("LexEntry", "LexSense", "LexExampleSentence", "MoForm"):
            rec = categories._CustomFieldRecord(cls, "Any field", 5100,
                                                field_type=CPT_STRING)
            status, _ = categories.classify_custom_field(rec, tgt)
            assert status == "NEW", f"Expected NEW for empty {cls}"


class TestEnumerateSourceWithTypeInfo:
    """custom_fields_enumerate_source populates field_type and list_root_guid.

    RED until T006 extends _enumerate_custom_fields to unpack the 4-tuple.
    """

    def _ctx(self, src, tgt) -> RunContext:
        return RunContext(
            source_handle=src, source_project_name="Src", source_project_path="/s",
            target_handle=tgt, target_project_name="Tgt", target_project_path="/t",
            run_id="GT-016-T005", started_at="2026-07-04T00:00:00",
        )

    def test_enumerate_populates_field_type(self) -> None:
        src = make_source(
            entry_fields=[(5100, "Noun class", CPT_STRING, "")],
        )
        tgt = make_target()
        sel = Selection(categories={})
        records = categories.custom_fields_enumerate_source(self._ctx(src, tgt), sel)
        assert len(records) == 1
        assert records[0].field_type == CPT_STRING

    def test_enumerate_populates_list_root_guid(self) -> None:
        list_guid = "deadbeef-0000-0000-0000-000000000001"
        src = make_source(
            sense_fields=[(5101, "Tone melody", CPT_REFATOMIC, list_guid)],
        )
        tgt = make_target()
        sel = Selection(categories={})
        records = categories.custom_fields_enumerate_source(self._ctx(src, tgt), sel)
        assert len(records) == 1
        assert records[0].list_root_guid == list_guid

    def test_enumerate_all_four_levels(self) -> None:
        src = make_source(
            entry_fields=[(5100, "F1", CPT_STRING, "")],
            sense_fields=[(5101, "F2", CPT_INTEGER, "")],
            example_fields=[(5102, "F3", CPT_BOOLEAN, "")],
            moform_fields=[(5103, "F4", CPT_MULTIUNICODE, "")],
        )
        tgt = make_target()
        sel = Selection(categories={})
        records = categories.custom_fields_enumerate_source(self._ctx(src, tgt), sel)
        assert len(records) == 4
        by_cls = {r.owner_class: r for r in records}
        assert by_cls["LexEntry"].field_type == CPT_STRING
        assert by_cls["LexSense"].field_type == CPT_INTEGER
        assert by_cls["LexExampleSentence"].field_type == CPT_BOOLEAN
        assert by_cls["MoForm"].field_type == CPT_MULTIUNICODE
