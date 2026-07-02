"""T072: Affix tree-picker convenience-toggle semantics + selection helpers (T073).

Pure-Python tests against `Lib/selection.py`. Verify that checking a template
implicitly selects every affix under it (via slot membership), checking a
slot pulls in just that slot's affixes, and per-affix checks still work
inside any branch.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.models import GrammarCategory, Selection
from gramtrans.Lib.selection import (
    PickerState,
    SourceAffixInventory,
    build_selection,
    compute_required_affixes,
    compute_required_templates,
)


# ============================================================================
# Fixtures: a small affix inventory
# ============================================================================
#
#   Template T1
#     Slot S1  -> a1, a2
#     Slot S2  -> a3
#   Template T2
#     Slot S3  -> a4
#   Unbound: aU1, aU2


INV = SourceAffixInventory(
    template_to_slots={
        "T1": ("S1", "S2"),
        "T2": ("S3",),
    },
    slot_to_affixes={
        "S1": ("a1", "a2"),
        "S2": ("a3",),
        "S3": ("a4",),
    },
    unbound_affixes=frozenset({"aU1", "aU2"}),
)


# ============================================================================
# compute_required_affixes
# ============================================================================

def test_checking_template_pulls_in_all_descendant_affixes() -> None:
    picker = PickerState(checked_templates=frozenset({"T1"}))
    affixes = compute_required_affixes(picker, INV)
    assert affixes == frozenset({"a1", "a2", "a3"})


def test_checking_slot_pulls_in_only_that_slots_affixes() -> None:
    picker = PickerState(checked_slots=frozenset({"S1"}))
    affixes = compute_required_affixes(picker, INV)
    assert affixes == frozenset({"a1", "a2"})


def test_checking_individual_affix_picks_only_that_affix() -> None:
    picker = PickerState(checked_affixes=frozenset({"a1"}))
    assert compute_required_affixes(picker, INV) == frozenset({"a1"})


def test_unbound_affix_pick_works() -> None:
    picker = PickerState(checked_affixes=frozenset({"aU1"}))
    assert compute_required_affixes(picker, INV) == frozenset({"aU1"})


def test_multi_level_picks_union() -> None:
    """Template T2 (→ a4) + slot S1 (→ a1, a2) + bare affix aU1."""
    picker = PickerState(
        checked_templates=frozenset({"T2"}),
        checked_slots=frozenset({"S1"}),
        checked_affixes=frozenset({"aU1"}),
    )
    assert compute_required_affixes(picker, INV) == frozenset({"a4", "a1", "a2", "aU1"})


def test_unknown_guids_are_ignored() -> None:
    """Defensive: GUIDs the inventory doesn't know about don't crash and
    don't appear in the result."""
    picker = PickerState(
        checked_templates=frozenset({"ghost-template"}),
        checked_affixes=frozenset({"ghost-affix"}),
    )
    assert compute_required_affixes(picker, INV) == frozenset()


# ============================================================================
# compute_required_templates
# ============================================================================

def test_only_explicit_template_picks_become_template_picks() -> None:
    """Slot or affix picks do NOT pull their parent template in."""
    picker = PickerState(
        checked_slots=frozenset({"S1"}),
        checked_affixes=frozenset({"a3"}),
    )
    assert compute_required_templates(picker, INV) == frozenset()


def test_explicit_template_picks_propagate() -> None:
    picker = PickerState(checked_templates=frozenset({"T1", "T2"}))
    assert compute_required_templates(picker, INV) == frozenset({"T1", "T2"})


# ============================================================================
# build_selection
# ============================================================================

def test_build_selection_sets_affixes_category_when_picks_present() -> None:
    picker = PickerState(checked_affixes=frozenset({"a1"}))
    sel = build_selection(picker, INV)
    assert sel.affix_picks == frozenset({"a1"})
    assert sel.categories.get(GrammarCategory.AFFIXES) is True
    # No templates picked → AFFIX_TEMPLATES not in categories
    assert sel.categories.get(GrammarCategory.AFFIX_TEMPLATES) is not True


def test_build_selection_sets_templates_category_when_picks_present() -> None:
    picker = PickerState(checked_templates=frozenset({"T1"}))
    sel = build_selection(picker, INV)
    assert sel.template_picks == frozenset({"T1"})
    # T1 expansion pulled a1, a2, a3 into affix_picks too
    assert sel.affix_picks == frozenset({"a1", "a2", "a3"})
    assert sel.categories.get(GrammarCategory.AFFIX_TEMPLATES) is True
    assert sel.categories.get(GrammarCategory.AFFIXES) is True


def test_build_selection_propagates_extra_categories() -> None:
    picker = PickerState()
    sel = build_selection(
        picker,
        INV,
        extra_categories=(GrammarCategory.CUSTOM_FIELDS, GrammarCategory.STEM_NAMES),
    )
    assert sel.categories[GrammarCategory.CUSTOM_FIELDS] is True
    assert sel.categories[GrammarCategory.STEM_NAMES] is True


def test_build_selection_respects_include_closure_default() -> None:
    sel = build_selection(PickerState(), INV)
    assert sel.include_closure is True


def test_build_selection_respects_include_closure_false() -> None:
    sel = build_selection(PickerState(), INV, include_closure=False)
    assert sel.include_closure is False


# ============================================================================
# Edge cases — tests 7-9 from the extension task
# ============================================================================

def test_build_selection_empty_picker_and_no_extras_returns_empty_categories() -> None:
    """build_selection with an all-default PickerState and no extra_categories
    must return a Selection whose categories dict is empty (not just falsy)
    and whose pick sets are both empty frozensets."""
    sel = build_selection(PickerState(), INV)
    assert sel.categories == {}
    assert len(sel.categories) == 0
    assert sel.include_closure is True
    assert sel.affix_picks == frozenset()
    assert sel.template_picks == frozenset()


def test_compute_required_affixes_closed_under_union() -> None:
    """compute_required_affixes(p1 | p2, inv) == result(p1, inv) | result(p2, inv).

    Uses two non-overlapping picker states against the shared INV fixture.
    """
    p1 = PickerState(checked_templates=frozenset({"T1"}))       # -> a1, a2, a3
    p2 = PickerState(checked_affixes=frozenset({"aU1", "aU2"})) # -> aU1, aU2

    result_p1 = compute_required_affixes(p1, INV)
    result_p2 = compute_required_affixes(p2, INV)

    # Union picker: combine all checked sets.
    p_union = PickerState(
        checked_templates=p1.checked_templates | p2.checked_templates,
        checked_slots=p1.checked_slots | p2.checked_slots,
        checked_affixes=p1.checked_affixes | p2.checked_affixes,
    )
    result_union = compute_required_affixes(p_union, INV)

    assert result_union == result_p1 | result_p2


def test_all_affix_guids_deduplicates_guid_in_slot_and_unbound() -> None:
    """SourceAffixInventory.all_affix_guids() returns a set union of slot affixes
    and unbound affixes; if a GUID appears in both, it must appear only once."""
    duplicate_guid = "shared-affix"
    inv = SourceAffixInventory(
        template_to_slots={"T1": ("S1",)},
        slot_to_affixes={"S1": (duplicate_guid, "a2")},
        unbound_affixes=frozenset({duplicate_guid, "aU1"}),
    )
    result = inv.all_affix_guids()
    # The duplicate appears exactly once (it's a frozenset).
    assert result.count if False else True  # frozenset has no .count — just verify type
    assert isinstance(result, frozenset)
    assert duplicate_guid in result
    # Total unique guids: shared-affix, a2, aU1 = 3
    assert result == frozenset({duplicate_guid, "a2", "aU1"})
