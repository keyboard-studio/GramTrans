"""Tests for ConflictMode model extension (Phase 3c, Refinement 4; updated 022).

Covers:
- ConflictMode enum {ADD_NEW, LINK, UPDATE, OVERWRITE} (022: MERGE renamed to LINK)
- category_conflict_modes field on Selection (back-compat)
- Selection.conflict_mode_for() Layer-1 defaults
- _DEFAULT_CONFLICT_MODES Layer-1 table correctness
- Layer-2 per-item IsProtected gating (v7.0.0 GOLD unlock: no longer downgrades
  to LINK -- keeps current_mode; failed-cast -> permissive)
- apply_isprotected_layer2 helper
- Backward-compat shim: persisted "merge" -> UPDATE (022 T004; v7.0.0)
- Confirm-on-Move gate: excluded_lossy_count() > 0 triggers confirmation
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.models import (
    ConflictMode,
    GrammarCategory,
    RunContext,
    RunPlan,
    Selection,
    WSMapping,
    _DEFAULT_CONFLICT_MODES,
)
from gramtrans.Lib.protection import (
    _is_protected,
    apply_isprotected_layer2,
)

# _allowed_modes and _GOLD_RESERVED are wizard-layer helpers; import lazily in
# the specific test class to avoid importing PyQt6 at module level.
def _get_wizard_helpers():
    from gramtrans.Lib.ui.selection_wizard import _allowed_modes, _GOLD_RESERVED
    return _allowed_modes, _GOLD_RESERVED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx():
    return RunContext(
        source_handle=object(),
        source_project_name="Src",
        source_project_path="/src",
        target_handle=object(),
        target_project_name="Tgt",
        target_project_path="/tgt",
        run_id="GT-20260701-120000",
        started_at="2026-07-01T12:00:00",
    )


# ===========================================================================
# ConflictMode enum
# ===========================================================================

class TestConflictModeEnum:
    def test_four_members(self):
        """022: enum now has four members (ADD_NEW, LINK, UPDATE, OVERWRITE)."""
        members = list(ConflictMode)
        assert len(members) == 4

    def test_values(self):
        assert ConflictMode.ADD_NEW.value == "add_new"
        assert ConflictMode.LINK.value == "link"      # 022: was MERGE="merge"
        assert ConflictMode.UPDATE.value == "update"  # 022: new non-destructive intent
        assert ConflictMode.OVERWRITE.value == "overwrite"

    def test_merge_member_absent(self):
        """022: ConflictMode.MERGE must no longer exist."""
        assert not hasattr(ConflictMode, "MERGE"), (
            "ConflictMode.MERGE should have been renamed to LINK in 022"
        )


# ===========================================================================
# Selection.category_conflict_modes back-compat
# ===========================================================================

class TestSelectionConflictModesBackCompat:
    def test_default_empty_category_conflict_modes(self):
        sel = Selection()
        assert sel.category_conflict_modes == {}

    def test_existing_construction_unchanged(self):
        """Old-style Selection with no conflict_modes must still construct fine."""
        sel = Selection(
            categories={GrammarCategory.POS: True},
            include_closure=True,
            enable_overwrite=False,
        )
        assert sel.is_on(GrammarCategory.POS)
        assert sel.category_conflict_modes == {}

    def test_explicit_conflict_mode_stored(self):
        modes = {GrammarCategory.POS: ConflictMode.OVERWRITE}
        sel = Selection(category_conflict_modes=modes)
        assert sel.category_conflict_modes[GrammarCategory.POS] == ConflictMode.OVERWRITE

    def test_conflict_mode_for_falls_back_to_layer1_default(self):
        sel = Selection()
        # POS is GOLD_RESERVED -> default UPDATE (v7.0.0 GOLD unlock; was LINK)
        assert sel.conflict_mode_for(GrammarCategory.POS) == ConflictMode.UPDATE

    def test_conflict_mode_for_explicit_overrides_default(self):
        sel = Selection(
            category_conflict_modes={GrammarCategory.AFFIXES: ConflictMode.OVERWRITE}
        )
        assert sel.conflict_mode_for(GrammarCategory.AFFIXES) == ConflictMode.OVERWRITE

    def test_conflict_mode_for_multi_instance_default_update(self):
        """022: MULTI_INSTANCE default is UPDATE (was ADD_NEW)."""
        sel = Selection()
        # AFFIXES is MULTI_INSTANCE -> default UPDATE (022 Ruling)
        assert sel.conflict_mode_for(GrammarCategory.AFFIXES) == ConflictMode.UPDATE

    def test_conflict_mode_for_custom_fields_default_link(self):
        sel = Selection()
        # CUSTOM_FIELDS: conservative default LINK (022: was MERGE)
        assert sel.conflict_mode_for(GrammarCategory.CUSTOM_FIELDS) == ConflictMode.LINK


# ===========================================================================
# Layer-1 default table (_DEFAULT_CONFLICT_MODES)
# ===========================================================================

class TestLayer1DefaultTable:
    """Verify every GrammarCategory has a default and the key categories
    are classified correctly per spec section (h)."""

    def test_every_grammar_category_has_a_default(self):
        for cat in GrammarCategory:
            assert cat in _DEFAULT_CONFLICT_MODES, (
                f"{cat} missing from _DEFAULT_CONFLICT_MODES"
            )

    def test_multi_instance_default_update(self):
        """022: MULTI_INSTANCE default is UPDATE (was ADD_NEW)."""
        multi = [
            GrammarCategory.AFFIXES,
            GrammarCategory.STEMS,
            GrammarCategory.SLOTS,
            GrammarCategory.AFFIX_TEMPLATES,
            GrammarCategory.INFLECTION_CLASSES,
            GrammarCategory.STEM_NAMES,
            GrammarCategory.EXCEPTION_FEATURES,
            GrammarCategory.ADHOC_COMPOUND_RULES,
            GrammarCategory.PHONEMES,
            GrammarCategory.NATURAL_CLASSES,
            GrammarCategory.PHONOLOGICAL_RULES,
            GrammarCategory.PH_ENVIRONMENT,
            GrammarCategory.STRATA,  # reclassified to MULTI_INSTANCE
        ]
        for cat in multi:
            assert _DEFAULT_CONFLICT_MODES[cat] == ConflictMode.UPDATE, (
                f"{cat} should be UPDATE (MULTI_INSTANCE default, 022) but got "
                f"{_DEFAULT_CONFLICT_MODES[cat]}"
            )

    def test_gold_reserved_default_update(self):
        """v7.0.0 GOLD unlock: GOLD_RESERVED default is UPDATE (was LINK).
        GOLD/reserved items are ordinary items and merge non-destructively."""
        gold = [
            GrammarCategory.GRAM_CATEGORIES,
            GrammarCategory.INFLECTION_FEATURES,
            GrammarCategory.VARIANT_TYPES,
            GrammarCategory.COMPLEX_FORM_TYPES,
            GrammarCategory.POS,
            GrammarCategory.PHONOLOGICAL_FEATURES,
            GrammarCategory.SEMANTIC_DOMAINS,
        ]
        for cat in gold:
            assert _DEFAULT_CONFLICT_MODES[cat] == ConflictMode.UPDATE, (
                f"{cat} should be UPDATE (GOLD unlock v7.0.0) but got "
                f"{_DEFAULT_CONFLICT_MODES[cat]}"
            )

    def test_custom_fields_conservative_link(self):
        """022: CUSTOM_FIELDS conservative default is LINK (was MERGE)."""
        assert _DEFAULT_CONFLICT_MODES[GrammarCategory.CUSTOM_FIELDS] == ConflictMode.LINK

    def test_writing_systems_check_link(self):
        """022: SINGLETON_NONDELETABLE -> LINK (was MERGE)."""
        assert _DEFAULT_CONFLICT_MODES[GrammarCategory.WRITING_SYSTEMS_CHECK] == ConflictMode.LINK


# ===========================================================================
# Layer-1 allowed_modes gating
# ===========================================================================

class TestAllowedModesLayer1:
    """_allowed_modes is in the wizard (Qt) layer; imported lazily here."""

    def test_gold_reserved_offers_all_four(self):
        """v7.0.0 GOLD unlock: GOLD_RESERVED offers the full mode set
        (ADD_NEW, LINK, UPDATE, OVERWRITE), not just LINK."""
        _allowed_modes, _GOLD_RESERVED = _get_wizard_helpers()
        for cat in _GOLD_RESERVED:
            modes = _allowed_modes(cat)
            assert modes == [
                ConflictMode.ADD_NEW,
                ConflictMode.LINK,
                ConflictMode.UPDATE,
                ConflictMode.OVERWRITE,
            ], (
                f"GOLD_RESERVED {cat} should offer all four modes, got {modes}"
            )
            assert ConflictMode.UPDATE in modes

    def test_multi_instance_offers_all_four(self):
        """022: MULTI_INSTANCE offers ADD_NEW, LINK, UPDATE, OVERWRITE."""
        _allowed_modes, _ = _get_wizard_helpers()
        modes = _allowed_modes(GrammarCategory.AFFIXES)
        assert ConflictMode.ADD_NEW in modes
        assert ConflictMode.LINK in modes
        assert ConflictMode.UPDATE in modes
        assert ConflictMode.OVERWRITE in modes

    def test_custom_fields_only_link(self):
        """022: CUSTOM_FIELDS offers only LINK (was MERGE)."""
        _allowed_modes, _ = _get_wizard_helpers()
        modes = _allowed_modes(GrammarCategory.CUSTOM_FIELDS)
        assert modes == [ConflictMode.LINK]

    def test_slots_offers_all_four(self):
        """022: SLOTS offers all four modes (was three)."""
        _allowed_modes, _ = _get_wizard_helpers()
        modes = _allowed_modes(GrammarCategory.SLOTS)
        assert len(modes) == 4


# ===========================================================================
# Layer-2 IsProtected gating
# ===========================================================================

class _FakeLCMObj:
    """Fake LCM object with configurable IsProtected."""
    def __init__(self, is_protected):
        self.IsProtected = is_protected


class _NoIsProtectedObj:
    """Fake LCM object WITHOUT IsProtected attribute."""
    pass


class _RaisingObj:
    """Fake LCM object whose IsProtected access raises."""
    @property
    def IsProtected(self):
        raise RuntimeError("cast failed")


class TestIsProtectedHelper:
    def test_protected_true_returns_true(self):
        obj = _FakeLCMObj(True)
        assert _is_protected(obj) is True

    def test_protected_false_returns_false(self):
        obj = _FakeLCMObj(False)
        assert _is_protected(obj) is False

    def test_absent_attribute_returns_false_permissive(self):
        """No IsProtected attr -> permissive (cannot prove protection)."""
        obj = _NoIsProtectedObj()
        assert _is_protected(obj) is False

    def test_raising_attribute_returns_false_permissive(self):
        """Failed cast / exception -> permissive."""
        obj = _RaisingObj()
        assert _is_protected(obj) is False

    def test_none_object_returns_false(self):
        assert _is_protected(None) is False


class TestApplyIsProtectedLayer2:
    def test_protected_item_keeps_current_mode(self):
        """v7.0.0 GOLD unlock: a protected item is ordinary -- Layer-2 NO LONGER
        downgrades it to LINK; current_mode is kept."""
        obj = _FakeLCMObj(True)
        result = apply_isprotected_layer2(
            GrammarCategory.AFFIXES, obj, ConflictMode.ADD_NEW
        )
        assert result == ConflictMode.ADD_NEW

    def test_non_protected_item_keeps_current_mode(self):
        """Non-protected item -> current_mode unchanged."""
        obj = _FakeLCMObj(False)
        result = apply_isprotected_layer2(
            GrammarCategory.AFFIXES, obj, ConflictMode.ADD_NEW
        )
        assert result == ConflictMode.ADD_NEW

    def test_failed_cast_permissive_keeps_mode(self):
        """Failed cast / absent attr -> permissive: current_mode unchanged."""
        obj = _RaisingObj()
        result = apply_isprotected_layer2(
            GrammarCategory.POS, obj, ConflictMode.OVERWRITE
        )
        assert result == ConflictMode.OVERWRITE

    def test_non_protected_full_set_available(self):
        """Non-protected item capped only by Layer 1.  AFFIXES + ADD_NEW -> stays ADD_NEW."""
        obj = _FakeLCMObj(False)
        for mode in (ConflictMode.ADD_NEW, ConflictMode.LINK, ConflictMode.UPDATE, ConflictMode.OVERWRITE):
            result = apply_isprotected_layer2(GrammarCategory.AFFIXES, obj, mode)
            assert result == mode

    def test_protected_keeps_overwrite(self):
        """v7.0.0 GOLD unlock: Protected + OVERWRITE is no longer downgraded;
        OVERWRITE is kept (the item is ordinary)."""
        obj = _FakeLCMObj(True)
        result = apply_isprotected_layer2(
            GrammarCategory.POS, obj, ConflictMode.OVERWRITE
        )
        assert result == ConflictMode.OVERWRITE

    def test_protected_keeps_update(self):
        """v7.0.0 GOLD unlock: Protected + UPDATE is no longer downgraded to
        LINK; UPDATE (non-destructive merge) is kept."""
        obj = _FakeLCMObj(True)
        result = apply_isprotected_layer2(
            GrammarCategory.POS, obj, ConflictMode.UPDATE
        )
        assert result == ConflictMode.UPDATE


# ===========================================================================
# Confirm-on-Move gate logic (excluded_lossy_count > 0 -> confirmation required)
# ===========================================================================

class TestConfirmOnMoveGateConflictMode:
    """Confirm-on-Move gate interacts correctly with ConflictMode-extended plans."""

    def _make_plan(self, lossy_count: int = 0) -> RunPlan:
        from gramtrans.Lib.models import ExcludedLossy
        import gramtrans.Lib.report  # noqa -- ensure build_from_plan attached
        lossy = tuple(
            ExcludedLossy(
                category=GrammarCategory.ENTRY,
                entry_guid=f"e{i:04d}",
                entry_label=f"entry{i}",
                dep_category=GrammarCategory.POS,
                dep_guid=f"p{i:04d}",
                dep_label="Verb",
                message=f"Entry 'entry{i}' will have no Part of Speech.",
            )
            for i in range(lossy_count)
        )
        sel = Selection(
            categories={GrammarCategory.AFFIXES: True},
            category_conflict_modes={GrammarCategory.AFFIXES: ConflictMode.LINK},
        )
        return RunPlan(
            context=_ctx(),
            selection=sel,
            ws_mapping=WSMapping(),
            excluded_lossy=lossy,
        )

    def test_zero_lossy_no_gate(self):
        plan = self._make_plan(0)
        assert plan.excluded_lossy_count() == 0
        assert (plan.excluded_lossy_count() > 0) is False

    def test_nonzero_lossy_gate_fires(self):
        plan = self._make_plan(2)
        assert plan.excluded_lossy_count() == 2
        assert (plan.excluded_lossy_count() > 0) is True

    def test_conflict_modes_preserved_in_selection(self):
        """022: explicit LINK stored on selection is preserved."""
        plan = self._make_plan(0)
        assert plan.selection.conflict_mode_for(GrammarCategory.AFFIXES) == ConflictMode.LINK


# ===========================================================================
# 022 T004: Backward-compat shim -- persisted "merge" -> UPDATE (v7.0.0)
# ===========================================================================

class TestBackwardCompatShim:
    """conflict_mode_for MUST remap the legacy "merge" string. Under
    constitution v7.0.0 the "merge" semantic is the non-destructive UPDATE."""

    def test_shim_string_merge_returns_update(self):
        """A stored string "merge" (old enum value) resolves to ConflictMode.UPDATE."""
        sel = Selection(
            category_conflict_modes={GrammarCategory.POS: "merge"}  # type: ignore[dict-item]
        )
        result = sel.conflict_mode_for(GrammarCategory.POS)
        assert result == ConflictMode.UPDATE, (
            f"Backward-compat shim must map 'merge' -> UPDATE, got {result!r}"
        )

    def test_shim_does_not_affect_link(self):
        """A stored ConflictMode.LINK is returned unchanged (no double-mapping)."""
        sel = Selection(
            category_conflict_modes={GrammarCategory.POS: ConflictMode.LINK}
        )
        assert sel.conflict_mode_for(GrammarCategory.POS) == ConflictMode.LINK

    def test_shim_does_not_affect_update(self):
        """A stored ConflictMode.UPDATE is returned unchanged."""
        sel = Selection(
            category_conflict_modes={GrammarCategory.AFFIXES: ConflictMode.UPDATE}
        )
        assert sel.conflict_mode_for(GrammarCategory.AFFIXES) == ConflictMode.UPDATE

    def test_shim_does_not_affect_overwrite(self):
        """A stored ConflictMode.OVERWRITE is returned unchanged."""
        sel = Selection(
            category_conflict_modes={GrammarCategory.AFFIXES: ConflictMode.OVERWRITE}
        )
        assert sel.conflict_mode_for(GrammarCategory.AFFIXES) == ConflictMode.OVERWRITE


# ===========================================================================
# 022 T026: UPDATE semantic tests (moved to test_update_semantic.py)
# Stub assertion here to confirm UPDATE is available as ConflictMode member.
# ===========================================================================

class TestUpdateMemberExists:
    def test_update_is_conflict_mode_member(self):
        assert ConflictMode.UPDATE.value == "update"

    def test_link_is_conflict_mode_member(self):
        assert ConflictMode.LINK.value == "link"

    def test_multi_instance_default_is_update(self):
        """022 Ruling: MULTI_INSTANCE categories default to UPDATE."""
        sel = Selection()
        assert sel.conflict_mode_for(GrammarCategory.STEMS) == ConflictMode.UPDATE
        assert sel.conflict_mode_for(GrammarCategory.AFFIXES) == ConflictMode.UPDATE

    def test_gold_default_is_update(self):
        """v7.0.0 GOLD unlock: GOLD_RESERVED categories default to UPDATE
        (ordinary-item non-destructive merge), not LINK."""
        sel = Selection()
        assert sel.conflict_mode_for(GrammarCategory.POS) == ConflictMode.UPDATE
        assert sel.conflict_mode_for(GrammarCategory.GRAM_CATEGORIES) == ConflictMode.UPDATE
