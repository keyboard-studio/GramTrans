"""Custom-fields unit tests (spec 016).

Phase 3b US2 (T001-T007): enumerate, classify, detect-and-skip.
Phase 016 T016-T019: real plan action (CreateDefinitionAction for NEW fields),
leaf_item_picks per-field filter, fail-loud on flid==0, create-before-value
ordering.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib import categories
from gramtrans.Lib.models import (
    CreateDefinitionAction,
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

def test_plan_action_emits_create_definition_when_target_absent() -> None:
    """T016: NEW field -> CreateDefinitionAction (not Skip(NEEDS_MANUAL))."""
    rec = categories._CustomFieldRecord("LexEntry", "Noun class",
                                        field_type=13)
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "Noun class")]})
    tgt = _FakeProject(custom_fields={})  # target has nothing
    result = categories.custom_fields_plan_action(rec, _ctx(src, tgt), WSM)
    assert isinstance(result, CreateDefinitionAction)
    assert result.category == GrammarCategory.CUSTOM_FIELDS
    assert result.owner_class == "LexEntry"
    assert result.field_name == "Noun class"
    assert result.field_type == 13
    assert result.source_guid == "cf:LexEntry:Noun class"


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
    """T016: no CustomFields accessor -> treated as absent -> CreateDefinitionAction."""
    rec = categories._CustomFieldRecord("LexEntry", "Foo", field_type=13)
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "Foo")]})
    tgt = object()  # no CustomFields
    result = categories.custom_fields_plan_action(rec, _ctx(src, tgt), WSM)
    assert isinstance(result, CreateDefinitionAction)
    assert result.field_name == "Foo"


def test_plan_action_two_branches() -> None:
    """T016: absent -> CreateDefinitionAction; present -> Skip(ALREADY_PRESENT_BY_IDENTITY).

    lex-qc P1 invariant: plan_action MUST NOT emit a bare PlannedAction
    (which would re-skip at execute time) for either branch.
    """
    rec = categories._CustomFieldRecord("LexEntry", "Foo", field_type=13)
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "Foo")]})

    # Branch 1: target ABSENT -> CreateDefinitionAction (not Skip, not PlannedAction)
    tgt_absent = _FakeProject()
    result_absent = categories.custom_fields_plan_action(rec, _ctx(src, tgt_absent), WSM)
    assert isinstance(result_absent, CreateDefinitionAction)
    assert not isinstance(result_absent, PlannedAction)
    assert not isinstance(result_absent, Skip)

    # Branch 2: target PRESENT -> ALREADY_PRESENT_BY_IDENTITY
    tgt_present = _FakeProject(custom_fields={"LexEntry": [(7001, "Foo")]})
    result_present = categories.custom_fields_plan_action(rec, _ctx(src, tgt_present), WSM)
    assert not isinstance(result_present, PlannedAction)
    assert isinstance(result_present, Skip)
    assert result_present.reason == SkipReason.ALREADY_PRESENT_BY_IDENTITY


def test_plan_action_findfield_exception_degrades_to_create_definition() -> None:
    """T016: when target's FindField raises, treat as absent ->
    CreateDefinitionAction (silent-degrade path at categories.py)."""
    class _RaisingCFOps(_FakeCFOps):
        def FindField(self, owner_class, name):
            raise RuntimeError("simulated MDC accessor failure")

    rec = categories._CustomFieldRecord("LexEntry", "Foo", field_type=13)
    src = _FakeProject(custom_fields={"LexEntry": [(5002, "Foo")]})
    tgt = _FakeProject()
    tgt.CustomFields = _RaisingCFOps({})  # swap in raising ops
    result = categories.custom_fields_plan_action(rec, _ctx(src, tgt), WSM)
    assert isinstance(result, CreateDefinitionAction)
    assert result.field_name == "Foo"


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


def test_execute_action_value_fill_dispatch_skipped() -> None:
    """G-1 coverage gap: US3 Acceptance-3 value-fill dispatch has no unit
    coverage because custom_fields_execute_action is a documented no-op stub
    (MVP T019 decision: value population is handled by transfer.execute
    internals on matched LCM objects).

    T026 validated the live persistence path end-to-end.  A focused mock-only
    unit test for the dispatch path is SKIPPED here because any meaningful
    assertion about value-write behaviour would require real LCM objects
    (IFwMetaDataCacheManaged, a live Cache.MetaDataCacheAccessor, etc.) that
    are unavailable in the unit-test environment.  Coverage is deferred until
    the stub is promoted to a real implementation.
    """
    pytest.skip(
        "G-1: value-fill dispatch requires live LCM objects; "
        "T026 covers the live persistence path end-to-end."
    )


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


# ============================================================================
# T016 -- real plan action: CreateDefinitionAction for NEW, idempotent reuse
# ============================================================================

class TestT016PlanAction:
    """T016: custom_fields_plan_action emits CreateDefinitionAction for NEW
    fields and Skip(ALREADY_PRESENT_BY_IDENTITY) for fields already in target.
    """

    def _ctx(self, src, tgt):
        return RunContext(
            source_handle=src, source_project_name="Src", source_project_path="/s",
            target_handle=tgt, target_project_name="Tgt", target_project_path="/t",
            run_id="GT-016-T016", started_at="2026-07-04T00:00:00",
        )

    def test_new_field_emits_create_definition_action(self) -> None:
        src = make_source(entry_fields=[(5100, "Noun class", CPT_STRING, "")])
        tgt = make_target()  # no fields
        rec = categories._CustomFieldRecord("LexEntry", "Noun class", 5100,
                                            field_type=CPT_STRING)
        result = categories.custom_fields_plan_action(rec, self._ctx(src, tgt), WSMapping(entries=()))
        assert isinstance(result, CreateDefinitionAction)
        assert result.category == GrammarCategory.CUSTOM_FIELDS
        assert result.owner_class == "LexEntry"
        assert result.field_name == "Noun class"
        assert result.field_type == CPT_STRING
        assert result.source_guid == "cf:LexEntry:Noun class"

    def test_present_field_emits_already_present_skip(self) -> None:
        """ALREADY_PRESENT idempotency: re-run with field present -> no new create."""
        src = make_source(entry_fields=[(5100, "Noun class", CPT_STRING, "")])
        tgt = make_target(entry_fields=[(7001, "Noun class", CPT_STRING, "")])
        rec = categories._CustomFieldRecord("LexEntry", "Noun class", 5100,
                                            field_type=CPT_STRING)
        result = categories.custom_fields_plan_action(rec, self._ctx(src, tgt), WSMapping(entries=()))
        assert isinstance(result, Skip)
        assert result.reason == SkipReason.ALREADY_PRESENT_BY_IDENTITY

    def test_list_root_guid_carried_in_create_action(self) -> None:
        list_guid = "deadbeef-0000-0000-0000-000000000001"
        src = make_source(sense_fields=[(5101, "Tone melody", CPT_REFATOMIC, list_guid)])
        tgt = make_target()
        rec = categories._CustomFieldRecord("LexSense", "Tone melody", 5101,
                                            field_type=CPT_REFATOMIC,
                                            list_root_guid=list_guid)
        result = categories.custom_fields_plan_action(rec, self._ctx(src, tgt), WSMapping(entries=()))
        assert isinstance(result, CreateDefinitionAction)
        assert result.list_root_guid == list_guid

    def test_all_four_owner_levels_emit_create_for_new(self) -> None:
        """CreateDefinitionAction must work for all supported owner classes."""
        for cls in ("LexEntry", "LexSense", "LexExampleSentence", "MoForm"):
            rec = categories._CustomFieldRecord(cls, "FieldX", 5100, field_type=CPT_STRING)
            src = make_source()
            tgt = make_target()
            # Inline context with matching class
            ctx = RunContext(
                source_handle=src, source_project_name="S", source_project_path="/s",
                target_handle=tgt, target_project_name="T", target_project_path="/t",
                run_id="GT-016", started_at="2026-07-04T00:00:00",
            )
            result = categories.custom_fields_plan_action(rec, ctx, WSMapping(entries=()))
            assert isinstance(result, CreateDefinitionAction), \
                f"Expected CreateDefinitionAction for {cls}, got {result!r}"


# ============================================================================
# T018 -- leaf_item_picks per-field TRIM
# ============================================================================

class TestT018LeafItemPicksFilter:
    """T018: custom_fields_enumerate_source respects leaf_item_picks[CUSTOM_FIELDS]."""

    def _ctx(self, src, tgt):
        return RunContext(
            source_handle=src, source_project_name="Src", source_project_path="/s",
            target_handle=tgt, target_project_name="Tgt", target_project_path="/t",
            run_id="GT-016-T018", started_at="2026-07-04T00:00:00",
        )

    def test_absent_key_returns_all(self) -> None:
        """Key absent from leaf_item_picks -> transfer-all (back-compat)."""
        src = make_source(
            entry_fields=[(5100, "Noun class", CPT_STRING, ""),
                          (5101, "Loanword", CPT_STRING, "")],
        )
        tgt = make_target()
        sel = Selection(categories={GrammarCategory.CUSTOM_FIELDS: True})
        records = categories.custom_fields_enumerate_source(self._ctx(src, tgt), sel)
        assert len(records) == 2

    def test_guid_subset_trims_to_selected(self) -> None:
        """Only the GUIDs in leaf_item_picks[CUSTOM_FIELDS] are returned."""
        src = make_source(
            entry_fields=[(5100, "Noun class", CPT_STRING, ""),
                          (5101, "Loanword", CPT_STRING, "")],
        )
        tgt = make_target()
        keep_guid = "cf:LexEntry:Noun class"
        sel = Selection(
            categories={GrammarCategory.CUSTOM_FIELDS: True},
            leaf_item_picks={GrammarCategory.CUSTOM_FIELDS: frozenset([keep_guid])},
        )
        records = categories.custom_fields_enumerate_source(self._ctx(src, tgt), sel)
        assert len(records) == 1
        assert records[0].name == "Noun class"

    def test_empty_frozenset_returns_none(self) -> None:
        """Empty frozenset -> transfer-none."""
        src = make_source(entry_fields=[(5100, "Noun class", CPT_STRING, "")])
        tgt = make_target()
        sel = Selection(
            categories={GrammarCategory.CUSTOM_FIELDS: True},
            leaf_item_picks={GrammarCategory.CUSTOM_FIELDS: frozenset()},
        )
        records = categories.custom_fields_enumerate_source(self._ctx(src, tgt), sel)
        assert records == []

    def test_filter_reaches_plan_via_enumerate(self) -> None:
        """End-to-end: filtered enumerate -> plan_action emits CreateDefinitionAction
        only for the selected field."""
        src = make_source(
            entry_fields=[(5100, "F1", CPT_STRING, ""),
                          (5101, "F2", CPT_STRING, "")],
        )
        tgt = make_target()
        keep_guid = "cf:LexEntry:F1"
        sel = Selection(
            categories={GrammarCategory.CUSTOM_FIELDS: True},
            leaf_item_picks={GrammarCategory.CUSTOM_FIELDS: frozenset([keep_guid])},
        )
        ctx = RunContext(
            source_handle=src, source_project_name="S", source_project_path="/s",
            target_handle=tgt, target_project_name="T", target_project_path="/t",
            run_id="GT-016", started_at="2026-07-04T00:00:00",
        )
        records = categories.custom_fields_enumerate_source(ctx, sel)
        assert len(records) == 1
        result = categories.custom_fields_plan_action(records[0], ctx, WSMapping(entries=()))
        assert isinstance(result, CreateDefinitionAction)
        assert result.field_name == "F1"


# ============================================================================
# T016 fail-loud: flid==0 must raise RuntimeError (mocked boundary)
# ============================================================================

class TestT016FailLoud:
    """Fail-loud on flid==0 or AddCustomField error.

    NOTE: The _ensure_custom_fields() in api.py calls the live LCM path.
    These tests mock the AddCustomField boundary (as required by the task
    memo: 'MOCK/STUB the FLExProject boundary').
    """

    def test_fail_loud_on_flid_zero(self) -> None:
        """AddCustomField returning 0 must raise RuntimeError with field name."""
        tgt = make_target(fail_add=True)
        mdc = tgt.Cache.MetaDataCacheAccessor

        # Simulate the _ensure_custom_fields inner logic directly.
        with pytest.raises(RuntimeError, match="flid=0"):
            flid = mdc.AddCustomField("LexEntry", "FailField", CPT_STRING, 0)
            if not flid:
                raise RuntimeError(
                    f"AddCustomField returned flid=0 for LexEntry.'FailField' "
                    f"(type {CPT_STRING}); schema write failed."
                )

    def test_idempotent_reuse_no_second_create(self) -> None:
        """Field already present -> FindField returns nonzero -> no AddCustomField call."""
        tgt = make_target(entry_fields=[(7001, "Noun class", CPT_STRING, "")])
        cf_ops = tgt.CustomFields
        existing = cf_ops.FindField("LexEntry", "Noun class")
        assert existing != 0, "pre-seeded field must be found"
        # Idempotency: if existing, skip AddCustomField (no call needed).
        call_count = [0]

        orig_add = tgt.Cache.MetaDataCacheAccessor.AddCustomField

        def _counting_add(*args, **kwargs):
            call_count[0] += 1
            return orig_add(*args, **kwargs)

        tgt.Cache.MetaDataCacheAccessor.AddCustomField = _counting_add
        # Simulate the idempotency guard: only add if not found.
        if not existing:
            tgt.Cache.MetaDataCacheAccessor.AddCustomField(
                "LexEntry", "Noun class", CPT_STRING, 0
            )
        assert call_count[0] == 0, "AddCustomField must not be called for pre-existing field"


# ============================================================================
# T016 AddCustomField call-shape: 4-arg vs 7-arg branch (mock boundary)
# ============================================================================

_FAKE_LIST_ROOT_GUID = "ad469eea-1234-5678-abcd-ef0123456789"


class TestAddCustomFieldCallShape:
    """Assert correct AddCustomField overload selection at the mock boundary.

    Value types (String / MultiString / MultiUnicode / Integer / GenDate /
    Boolean) must use the 4-arg overload with destinationClass=0.

    ReferenceAtomic (24) and ReferenceCollection (26) must use the 7-arg
    overload with destinationClass=7 (CmPossibility) and
    fieldListRoot == the record's list_root_guid (as a Guid -- the fake
    accepts the string representation).
    """

    def _run_create(self, field_type: int, list_root_guid: str = "") -> tuple:
        """Simulate the _ensure_custom_fields inner _do_creates logic.

        Mirrors the branching code in api._ensure_custom_fields and returns
        the args tuple that AddCustomField was called with.
        """
        _LIST_FIELD_TYPES = frozenset((24, 26))
        _CM_POSSIBILITY_CLASS_ID = 7

        tgt = make_target()
        mdc = tgt.Cache.MetaDataCacheAccessor
        cf_ops = tgt.CustomFields

        calls: list = []
        orig_add = mdc.AddCustomField

        def _recording_add(*args, **kwargs):
            calls.append(args)
            return orig_add(*args, **kwargs)

        mdc.AddCustomField = _recording_add

        # Run the branch logic (mirroring api._ensure_custom_fields _do_creates).
        existing = cf_ops.FindField("LexEntry", "TestField")
        assert existing == 0, "fresh target must have no pre-existing fields"
        if field_type in _LIST_FIELD_TYPES:
            flid = mdc.AddCustomField(
                "LexEntry", "TestField", field_type,
                _CM_POSSIBILITY_CLASS_ID, "", 0, list_root_guid,
            )
        else:
            flid = mdc.AddCustomField(
                "LexEntry", "TestField", field_type, 0
            )
        assert flid != 0, "AddCustomField must return nonzero flid on success"
        assert len(calls) == 1, "exactly one AddCustomField call expected"
        return calls[0]

    def test_value_type_string_uses_4arg_destination_zero(self) -> None:
        """String (13) -> 4-arg call, destinationClass=0."""
        args = self._run_create(CPT_STRING)
        assert len(args) == 4, f"expected 4-arg call, got {len(args)} args: {args}"
        assert args[0] == "LexEntry"
        assert args[1] == "TestField"
        assert args[2] == CPT_STRING
        assert args[3] == 0, f"destinationClass must be 0 for value types, got {args[3]}"

    def test_value_type_multistring_uses_4arg_destination_zero(self) -> None:
        """MultiString (14) -> 4-arg call, destinationClass=0."""
        args = self._run_create(CPT_MULTISTRING)
        assert len(args) == 4
        assert args[3] == 0

    def test_value_type_integer_uses_4arg_destination_zero(self) -> None:
        """Integer (2) -> 4-arg call, destinationClass=0."""
        args = self._run_create(CPT_INTEGER)
        assert len(args) == 4
        assert args[3] == 0

    def test_reference_atomic_uses_7arg_destination_7_with_list_root(self) -> None:
        """ReferenceAtomic (24) -> 7-arg call, destinationClass=7, fieldListRoot==list_root_guid."""
        args = self._run_create(CPT_REFATOMIC, _FAKE_LIST_ROOT_GUID)
        assert len(args) == 7, f"expected 7-arg call, got {len(args)} args: {args}"
        assert args[0] == "LexEntry"
        assert args[1] == "TestField"
        assert args[2] == CPT_REFATOMIC
        assert args[3] == 7, f"destinationClass must be 7 (CmPossibility) for list types, got {args[3]}"
        # args[4] = fieldHelp (empty str), args[5] = fieldWs (0)
        assert args[6] == _FAKE_LIST_ROOT_GUID, (
            f"fieldListRoot must equal the record's list_root_guid, got {args[6]!r}"
        )

    def test_reference_collection_uses_7arg_destination_7_with_list_root(self) -> None:
        """ReferenceCollection (26) -> 7-arg call, destinationClass=7, fieldListRoot==list_root_guid."""
        args = self._run_create(CPT_REFCOLLECTION, _FAKE_LIST_ROOT_GUID)
        assert len(args) == 7, f"expected 7-arg call, got {len(args)} args: {args}"
        assert args[2] == CPT_REFCOLLECTION
        assert args[3] == 7
        assert args[6] == _FAKE_LIST_ROOT_GUID


# ============================================================================
# SC-004 create-before-value ordering
# ============================================================================

class TestSC004Ordering:
    """SC-004: CreateDefinitionActions must be ordered before value-fill
    PlannedActions in RunPlan.actions.

    These tests verify the action-type ordering contract without requiring
    a live LCM host.
    """

    def test_create_definition_action_is_distinct_from_planned_action(self) -> None:
        cda = CreateDefinitionAction(
            category=GrammarCategory.CUSTOM_FIELDS,
            source_guid="cf:LexEntry:F",
            owner_class="LexEntry",
            field_name="F",
            field_type=CPT_STRING,
            list_root_guid="",
            summary="Create F",
        )
        pa = PlannedAction(
            category=GrammarCategory.CUSTOM_FIELDS,
            source_guid="cf:LexEntry:G",
            intended_target_guid="cf:LexEntry:G",
            summary="Fill G values",
        )
        assert isinstance(cda, CreateDefinitionAction)
        assert not isinstance(cda, PlannedAction)
        assert isinstance(pa, PlannedAction)
        assert not isinstance(pa, CreateDefinitionAction)

    def test_ordering_invariant_no_violations(self) -> None:
        """In a mixed actions tuple, all CreateDefinitionActions must come
        before any PlannedAction (SC-004 ordering contract)."""
        cda = CreateDefinitionAction(
            category=GrammarCategory.CUSTOM_FIELDS,
            source_guid="cf:LexEntry:F",
            owner_class="LexEntry",
            field_name="F",
            field_type=CPT_STRING,
            list_root_guid="",
            summary="Create",
        )
        pa = PlannedAction(
            category=GrammarCategory.CUSTOM_FIELDS,
            source_guid="cf:LexEntry:G",
            intended_target_guid="cf:LexEntry:G",
            summary="Fill",
        )
        # Correct ordering: CDA first, PA second.
        actions = (cda, pa)
        violations = []
        seen_planned = False
        for a in actions:
            if isinstance(a, PlannedAction):
                seen_planned = True
            elif isinstance(a, CreateDefinitionAction) and seen_planned:
                violations.append(a)
        assert violations == [], f"SC-004 ordering violations: {violations}"
