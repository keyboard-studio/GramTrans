"""T071 / T076: closure-off mode skip semantics (FR-013, Scenario F).

When `selection.include_closure=False`, items that the user explicitly
selected but whose dependencies are NOT also user-selected become
`Skip(reason=BARE_BONES_MISSING_CLOSURE)`. Items in not-selected categories
simply don't appear in the plan.

These tests share the recording-fake-target infrastructure from
test_preview_no_writes.py and reuse the LCM-helper monkeypatching pattern.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib import preview as preview_mod
from gramtrans.Lib.models import (
    GrammarCategory,
    RunContext,
    Selection,
    SkipReason,
    WSMapping,
)
from gramtrans.Lib.preview import build_run_plan


# ============================================================================
# Minimal fakes (independent copy of the test_preview_no_writes shapes)
# ============================================================================

class _Slot:
    def __init__(self, guid: str, name: str = "slot") -> None:
        self.guid = guid
        self._name = name


class _Template:
    def __init__(self, guid: str, prefix=(), suffix=(), pro=(), enc=()) -> None:
        self.guid = guid
        self.prefix_slots = prefix
        self.suffix_slots = suffix
        self.proclitic_slots = pro
        self.enclitic_slots = enc

    @property
    def concrete(self):
        return self


class _POS:
    def __init__(self, guid: str) -> None:
        self.guid = guid

    @property
    def concrete(self):
        return self


class _POSOps:
    def __init__(self, verb=None) -> None:
        self._verb = verb

    def Find(self, name):  # noqa: N802
        return self._verb if name == "Verb" else None

    def GetAll(self, recursive=False):  # noqa: N802
        # When the fake has a verb set, include it so the multi-POS walker
        # in preview.build_run_plan finds it via _select_source_poses.
        return [self._verb] if self._verb is not None else []

    def GetSyncableProperties(self, pos):  # noqa: N802
        return {}

    def GetAffixSlots(self, pos):  # noqa: N802
        return []


class _MorphRulesOps:
    def __init__(self, templates=()) -> None:
        self._tpls = list(templates)

    def GetAllAffixTemplatesForPOS(self, pos):  # noqa: N802
        return list(self._tpls)

    def GetSyncableProperties(self, tpl):  # noqa: N802
        return {}


class _Project:
    def __init__(self, name, verb=None, templates=()) -> None:
        self.name = name
        self.POS = _POSOps(verb=verb)
        self.MorphRules = _MorphRulesOps(templates=templates)

    def ProjectName(self):  # noqa: N802
        return self.name


@pytest.fixture
def _patch_lcm(monkeypatch):
    monkeypatch.setattr(preview_mod, "_guid_str", lambda obj: obj.guid)
    monkeypatch.setattr(preview_mod, "_unwrap", lambda obj: obj.concrete if hasattr(obj, "concrete") else obj)
    monkeypatch.setattr(preview_mod, "_slot_name", lambda slot: getattr(slot, "_name", "anon"))


def _ctx(src, tgt) -> RunContext:
    return RunContext(
        source_handle=src,
        source_project_name="Src",
        source_project_path="/src",
        target_handle=tgt,
        target_project_name="Tgt",
        target_project_path="/tgt",
        run_id="GT-20260619-150000",
        started_at="2026-06-19T15:00:00",
    )


def _src_with_full_verb():
    verb = _POS("verb-1")
    tpl = _Template("tpl-1", prefix=(_Slot("s-a", "AGR"),), suffix=(_Slot("s-b", "TNS"),))
    return _Project("src", verb=verb, templates=(tpl,))


# ============================================================================
# Tests
# ============================================================================

def test_closure_off_with_only_pos_selected_plans_only_pos(_patch_lcm):
    src = _src_with_full_verb()
    tgt = _Project("tgt")
    sel = Selection(
        categories={GrammarCategory.POS: True},
        include_closure=False,
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)
    cats = [a.category for a in plan.actions]
    assert cats == [GrammarCategory.POS]
    assert plan.skips == ()


def test_closure_off_with_pos_and_templates_no_slots_skips_template_bare_bones(_patch_lcm):
    """User picked POS + AFFIX_TEMPLATES but not SLOTS; closure off; template has
    slots → template becomes BARE_BONES_MISSING_CLOSURE skip."""
    src = _src_with_full_verb()
    tgt = _Project("tgt")
    sel = Selection(
        categories={
            GrammarCategory.POS: True,
            GrammarCategory.AFFIX_TEMPLATES: True,
        },
        include_closure=False,
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)

    action_cats = [a.category for a in plan.actions]
    assert GrammarCategory.POS in action_cats
    assert GrammarCategory.AFFIX_TEMPLATES not in action_cats
    assert GrammarCategory.SLOTS not in action_cats

    template_skips = [s for s in plan.skips if s.category == GrammarCategory.AFFIX_TEMPLATES]
    assert len(template_skips) == 1
    assert template_skips[0].reason == SkipReason.BARE_BONES_MISSING_CLOSURE
    assert "slots" in template_skips[0].detail


def test_closure_off_with_templates_only_skips_template_for_missing_owner_pos(_patch_lcm):
    """User picked TEMPLATES but not POS; closure off → template skipped
    because its owner POS isn't selected."""
    src = _src_with_full_verb()
    tgt = _Project("tgt")
    sel = Selection(
        categories={GrammarCategory.AFFIX_TEMPLATES: True},
        include_closure=False,
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)

    # No actions (POS not user-selected; template skipped; slots not selected)
    assert plan.actions == ()
    template_skips = [s for s in plan.skips if s.category == GrammarCategory.AFFIX_TEMPLATES]
    assert len(template_skips) == 1
    assert template_skips[0].reason == SkipReason.BARE_BONES_MISSING_CLOSURE
    assert "owner POS" in template_skips[0].detail


def test_closure_off_with_all_three_categories_selected_plans_all(_patch_lcm):
    """User picked POS + AFFIX_TEMPLATES + SLOTS; closure off; everything user-selected
    → all actions, no skips."""
    src = _src_with_full_verb()
    tgt = _Project("tgt")
    sel = Selection(
        categories={
            GrammarCategory.POS: True,
            GrammarCategory.AFFIX_TEMPLATES: True,
            GrammarCategory.SLOTS: True,
        },
        include_closure=False,
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)
    cats = sorted({a.category for a in plan.actions}, key=lambda c: c.value)
    assert GrammarCategory.POS in cats
    assert GrammarCategory.AFFIX_TEMPLATES in cats
    assert GrammarCategory.SLOTS in cats
    assert plan.skips == ()


def test_closure_on_pulls_in_everything_regardless(_patch_lcm):
    """Sanity: closure ON, user picked only POS → templates and slots still
    pulled in via closure."""
    src = _src_with_full_verb()
    tgt = _Project("tgt")
    sel = Selection(
        categories={GrammarCategory.POS: True},
        include_closure=True,
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)
    cats = {a.category for a in plan.actions}
    assert GrammarCategory.POS in cats
    assert GrammarCategory.AFFIX_TEMPLATES in cats
    assert GrammarCategory.SLOTS in cats
    # Templates and slots carry pulled_in_by because they came via closure.
    for a in plan.actions:
        if a.category != GrammarCategory.POS:
            assert a.pulled_in_by, f"{a.category.name} should be marked pulled-in"


def test_closure_off_template_with_no_slots_does_not_skip_for_slots(_patch_lcm):
    """A template with zero slots and closure off: doesn't need slot deps,
    so it plans normally as long as POS is selected."""
    verb = _POS("verb-1")
    empty_tpl = _Template("tpl-empty")  # no slots
    src = _Project("src", verb=verb, templates=(empty_tpl,))
    tgt = _Project("tgt")
    sel = Selection(
        categories={GrammarCategory.POS: True, GrammarCategory.AFFIX_TEMPLATES: True},
        include_closure=False,
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)
    cats = [a.category for a in plan.actions]
    assert GrammarCategory.AFFIX_TEMPLATES in cats
    assert plan.skips == ()
