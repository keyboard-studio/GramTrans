"""Phase 3c US5 empty-source UX (T067-T071).

For each of the five Phase 3c leaf categories -- AFFIXES, SLOTS,
AFFIX_TEMPLATES, STEMS, ADHOC_COMPOUND_RULES -- assert that enumerate_source
over an empty (or no-matching) source yields an empty enumeration, and that
"building a plan" over that empty enumeration produces no PlannedActions and
does not raise.

This exercises the empty-source UX contract: a source project that contains
no items of a category (either genuinely empty, or containing only items that
fail the category's filter) must degrade cleanly to a zero-action plan rather
than erroring.

All host-free: no Windows / LCM / pythonnet. The enumerate/plan-planning path
never touches SIL.LCModel for an empty enumeration (no GUID extraction, no
IPartOfSpeech cast happens when there is nothing to enumerate), so no
monkeypatching of categories._guid_str_from is required here.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from gramtrans.Lib import categories
from gramtrans.Lib.models import (
    GrammarCategory,
    PlannedAction,
    RunContext,
    Selection,
    WSMapping,
)


# ============================================================================
# Duck-typed source/target handles (all lowercase .guid where relevant)
# ============================================================================

def _lexdb_handle(entries=()):
    """Handle exposing the contract nav shape walked by
    categories._iter_lex_entries: handle.LangProject.LexDbOA.EntriesOC.
    Used for AFFIXES + STEMS (both enumerate over lex entries)."""
    return SimpleNamespace(
        LangProject=SimpleNamespace(
            LexDbOA=SimpleNamespace(EntriesOC=list(entries))
        )
    )


class _FakeMorphType:
    def __init__(self, is_affix: bool) -> None:
        self.IsAffixType = is_affix


class _FakeLexForm:
    def __init__(self, is_affix: bool) -> None:
        self.MorphTypeRA = _FakeMorphType(is_affix)


class _FakeEntry:
    """Minimal ILexEntry stand-in for the affix/stem partition."""

    def __init__(self, guid: str, is_affix: bool) -> None:
        self.guid = guid
        self.LexemeFormOA = _FakeLexForm(is_affix)
        self.MorphoSyntaxAnalysesOC = []
        self.SensesOS = []
        self.EntryRefsOS = []


class _FakePOS:
    """IPartOfSpeech stand-in exposing the slot/template owned collections."""

    def __init__(self, guid: str, slots=(), templates=()) -> None:
        self.guid = guid
        self.AffixSlotsOC = list(slots)
        self.AffixTemplatesOS = list(templates)

    @property
    def concrete(self):
        return self


class _FakePOSOps:
    def __init__(self, poses=()) -> None:
        self._poses = list(poses)

    def GetAll(self, recursive=True):
        return list(self._poses)


class _FakePOSProject:
    """Source/target handle for SLOTS + AFFIX_TEMPLATES (handle.POS.GetAll)."""

    def __init__(self, poses=()) -> None:
        self.POS = _FakePOSOps(poses)


class _FakeMorphData:
    def __init__(self, adhoc=(), compound=()) -> None:
        self.AdhocCoProhibitionsOS = list(adhoc)
        self.CompoundRulesOS = list(compound)


class _FakeRulesProject:
    """Source/target handle for ADHOC_COMPOUND_RULES
    (handle.Cache.LangProject.MorphologicalDataOA)."""

    def __init__(self, adhoc=(), compound=()) -> None:
        self.Cache = SimpleNamespace(
            LangProject=SimpleNamespace(
                MorphologicalDataOA=_FakeMorphData(adhoc, compound)
            )
        )


def _ctx(source, target) -> RunContext:
    ctx = RunContext(
        source_handle=source,
        source_project_name="Src",
        source_project_path="/src",
        target_handle=target,
        target_project_name="Tgt",
        target_project_path="/tgt",
        run_id="GT-20260706-010000",
        started_at="2026-07-06T01:00:00",
    )
    # Mirror preview.build_run_plan: attach the empty stash dicts that the
    # AFFIXES/STEMS plan_action paths write MSA-slot / EntryRef bindings into.
    object.__setattr__(ctx, "_msa_slot_bindings", {})
    object.__setattr__(ctx, "_lexentry_ref_bindings", {})
    return ctx


def _build_plan(bundle, ctx, selection):
    """Simulate plan building over an enumeration: enumerate the source, then
    call plan_action on each yielded piece, returning the list of PlannedActions.
    Must not raise. For an empty enumeration this returns []."""
    pieces = list(bundle["enumerate_source"](ctx, selection))
    actions = []
    for piece in pieces:
        result = bundle["plan_action"](piece, ctx, WSMapping())
        if isinstance(result, PlannedAction):
            actions.append(result)
    return pieces, actions


# ============================================================================
# T067 -- AFFIXES empty source
# ============================================================================

def test_affixes_empty_source_enumerates_and_plans_nothing() -> None:
    bundle = categories.for_category(GrammarCategory.AFFIXES)
    ctx = _ctx(_lexdb_handle([]), _lexdb_handle([]))

    pieces, actions = _build_plan(bundle, ctx, None)

    assert pieces == []
    assert actions == []


def test_affixes_no_matching_entries_enumerates_nothing() -> None:
    """A source that has entries but no affixes (only stems) enumerates empty."""
    bundle = categories.for_category(GrammarCategory.AFFIXES)
    src = _lexdb_handle([_FakeEntry("stem-1", is_affix=False),
                         _FakeEntry("stem-2", is_affix=False)])
    ctx = _ctx(src, _lexdb_handle([]))

    pieces, actions = _build_plan(bundle, ctx, None)

    assert pieces == []
    assert actions == []


# ============================================================================
# T068 -- SLOTS empty source
# ============================================================================

def test_slots_empty_source_enumerates_and_plans_nothing() -> None:
    """No POS at all in the source => no slots."""
    bundle = categories.for_category(GrammarCategory.SLOTS)
    ctx = _ctx(_FakePOSProject(poses=()), _FakePOSProject(poses=()))

    pieces, actions = _build_plan(bundle, ctx, None)

    assert pieces == []
    assert actions == []


def test_slots_pos_without_slots_enumerates_nothing() -> None:
    """A source POS exists but carries no AffixSlotsOC => empty enumeration."""
    bundle = categories.for_category(GrammarCategory.SLOTS)
    src = _FakePOSProject(poses=(_FakePOS("pos-verb", slots=()),))
    ctx = _ctx(src, _FakePOSProject(poses=()))

    pieces, actions = _build_plan(bundle, ctx, None)

    assert pieces == []
    assert actions == []


# ============================================================================
# T069 -- AFFIX_TEMPLATES empty source
# ============================================================================

def test_affix_templates_empty_source_enumerates_and_plans_nothing() -> None:
    bundle = categories.for_category(GrammarCategory.AFFIX_TEMPLATES)
    ctx = _ctx(_FakePOSProject(poses=()), _FakePOSProject(poses=()))

    pieces, actions = _build_plan(bundle, ctx, None)

    assert pieces == []
    assert actions == []


def test_affix_templates_pos_without_templates_enumerates_nothing() -> None:
    """A source POS exists but carries no AffixTemplatesOS => empty."""
    bundle = categories.for_category(GrammarCategory.AFFIX_TEMPLATES)
    src = _FakePOSProject(poses=(_FakePOS("pos-verb", templates=()),))
    ctx = _ctx(src, _FakePOSProject(poses=()))

    pieces, actions = _build_plan(bundle, ctx, None)

    assert pieces == []
    assert actions == []


# ============================================================================
# T070 -- STEMS empty source
# ============================================================================

def test_stems_empty_source_enumerates_and_plans_nothing() -> None:
    bundle = categories.for_category(GrammarCategory.STEMS)
    ctx = _ctx(_lexdb_handle([]), _lexdb_handle([]))

    pieces, actions = _build_plan(bundle, ctx, None)

    assert pieces == []
    assert actions == []


def test_stems_no_matching_entries_enumerates_nothing() -> None:
    """A source that has entries but no stems (only affixes) enumerates empty."""
    bundle = categories.for_category(GrammarCategory.STEMS)
    src = _lexdb_handle([_FakeEntry("aff-1", is_affix=True),
                         _FakeEntry("aff-2", is_affix=True)])
    ctx = _ctx(src, _lexdb_handle([]))

    pieces, actions = _build_plan(bundle, ctx, None)

    assert pieces == []
    assert actions == []


# ============================================================================
# T071 -- ADHOC_COMPOUND_RULES empty source
# ============================================================================

def test_adhoc_compound_rules_empty_source_enumerates_and_plans_nothing() -> None:
    bundle = categories.for_category(GrammarCategory.ADHOC_COMPOUND_RULES)
    ctx = _ctx(_FakeRulesProject(adhoc=(), compound=()),
               _FakeRulesProject(adhoc=(), compound=()))
    # adhoc_compound_rules_enumerate_source calls selection.leaf_picks_for
    # unconditionally, so pass a real Selection (absent key => transfer ALL).
    sel = Selection(categories={GrammarCategory.ADHOC_COMPOUND_RULES: True})

    pieces, actions = _build_plan(bundle, ctx, sel)

    assert pieces == []
    assert actions == []


# ============================================================================
# Cross-category sweep: every Phase 3c category degrades to a zero-action plan
# ============================================================================

def test_all_five_phase3c_categories_empty_source_zero_actions() -> None:
    cases = [
        (GrammarCategory.AFFIXES, _lexdb_handle([]), None),
        (GrammarCategory.SLOTS, _FakePOSProject(poses=()), None),
        (GrammarCategory.AFFIX_TEMPLATES, _FakePOSProject(poses=()), None),
        (GrammarCategory.STEMS, _lexdb_handle([]), None),
        (GrammarCategory.ADHOC_COMPOUND_RULES, _FakeRulesProject(),
         Selection(categories={GrammarCategory.ADHOC_COMPOUND_RULES: True})),
    ]
    for cat, src, sel in cases:
        bundle = categories.for_category(cat)
        ctx = _ctx(src, _empty_like(src))
        pieces, actions = _build_plan(bundle, ctx, sel)
        assert pieces == [], f"{cat.name}: expected empty enumeration"
        assert actions == [], f"{cat.name}: expected zero planned actions"


def _empty_like(src):
    """Return an empty target handle matching the shape of the source handle."""
    if isinstance(src, _FakePOSProject):
        return _FakePOSProject(poses=())
    if isinstance(src, _FakeRulesProject):
        return _FakeRulesProject()
    return _lexdb_handle([])
