"""Tests for ConflictMode model extension (Phase 3c, Refinement 4).

Covers:
- ConflictMode enum {ADD_NEW, MERGE, OVERWRITE}
- category_conflict_modes field on Selection (back-compat)
- Selection.conflict_mode_for() Layer-1 defaults
- _DEFAULT_CONFLICT_MODES Layer-1 table correctness
- Layer-2 per-item IsProtected gating (protected -> MERGE; non-protected -> full set;
  failed-cast -> permissive)
- apply_isprotected_layer2 helper
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
    def test_three_members(self):
        members = list(ConflictMode)
        assert len(members) == 3

    def test_values(self):
        assert ConflictMode.ADD_NEW.value == "add_new"
        assert ConflictMode.MERGE.value == "merge"
        assert ConflictMode.OVERWRITE.value == "overwrite"


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
        # POS is GOLD_RESERVED -> default MERGE
        assert sel.conflict_mode_for(GrammarCategory.POS) == ConflictMode.MERGE

    def test_conflict_mode_for_explicit_overrides_default(self):
        sel = Selection(
            category_conflict_modes={GrammarCategory.AFFIXES: ConflictMode.OVERWRITE}
        )
        assert sel.conflict_mode_for(GrammarCategory.AFFIXES) == ConflictMode.OVERWRITE

    def test_conflict_mode_for_multi_instance_default_add_new(self):
        sel = Selection()
        # AFFIXES is MULTI_INSTANCE -> default ADD_NEW
        assert sel.conflict_mode_for(GrammarCategory.AFFIXES) == ConflictMode.ADD_NEW

    def test_conflict_mode_for_custom_fields_default_merge(self):
        sel = Selection()
        # CUSTOM_FIELDS: conservative default MERGE
        assert sel.conflict_mode_for(GrammarCategory.CUSTOM_FIELDS) == ConflictMode.MERGE


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

    def test_multi_instance_default_add_new(self):
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
            assert _DEFAULT_CONFLICT_MODES[cat] == ConflictMode.ADD_NEW, (
                f"{cat} should be ADD_NEW (MULTI_INSTANCE) but got "
                f"{_DEFAULT_CONFLICT_MODES[cat]}"
            )

    def test_gold_reserved_default_merge(self):
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
            assert _DEFAULT_CONFLICT_MODES[cat] == ConflictMode.MERGE, (
                f"{cat} should be MERGE (GOLD_RESERVED) but got "
                f"{_DEFAULT_CONFLICT_MODES[cat]}"
            )

    def test_custom_fields_conservative_merge(self):
        assert _DEFAULT_CONFLICT_MODES[GrammarCategory.CUSTOM_FIELDS] == ConflictMode.MERGE

    def test_writing_systems_check_merge(self):
        # SINGLETON_NONDELETABLE -> MERGE
        assert _DEFAULT_CONFLICT_MODES[GrammarCategory.WRITING_SYSTEMS_CHECK] == ConflictMode.MERGE


# ===========================================================================
# Layer-1 allowed_modes gating
# ===========================================================================

class TestAllowedModesLayer1:
    """_allowed_modes is in the wizard (Qt) layer; imported lazily here."""

    def test_gold_reserved_only_merge_offered(self):
        _allowed_modes, _GOLD_RESERVED = _get_wizard_helpers()
        for cat in _GOLD_RESERVED:
            modes = _allowed_modes(cat)
            assert modes == [ConflictMode.MERGE], (
                f"GOLD_RESERVED {cat} should offer only MERGE, got {modes}"
            )

    def test_multi_instance_offers_all_three(self):
        _allowed_modes, _ = _get_wizard_helpers()
        modes = _allowed_modes(GrammarCategory.AFFIXES)
        assert ConflictMode.ADD_NEW in modes
        assert ConflictMode.MERGE in modes
        assert ConflictMode.OVERWRITE in modes

    def test_custom_fields_only_merge(self):
        _allowed_modes, _ = _get_wizard_helpers()
        modes = _allowed_modes(GrammarCategory.CUSTOM_FIELDS)
        assert modes == [ConflictMode.MERGE]

    def test_slots_offers_all_three(self):
        _allowed_modes, _ = _get_wizard_helpers()
        modes = _allowed_modes(GrammarCategory.SLOTS)
        assert len(modes) == 3


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
    def test_protected_item_downgrades_to_merge(self):
        """A protected item -> MERGE regardless of category default."""
        obj = _FakeLCMObj(True)
        result = apply_isprotected_layer2(
            GrammarCategory.AFFIXES, obj, ConflictMode.ADD_NEW
        )
        assert result == ConflictMode.MERGE

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
        for mode in (ConflictMode.ADD_NEW, ConflictMode.MERGE, ConflictMode.OVERWRITE):
            result = apply_isprotected_layer2(GrammarCategory.AFFIXES, obj, mode)
            assert result == mode

    def test_protected_overrides_overwrite(self):
        """Protected + OVERWRITE -> downgraded to MERGE."""
        obj = _FakeLCMObj(True)
        result = apply_isprotected_layer2(
            GrammarCategory.POS, obj, ConflictMode.OVERWRITE
        )
        assert result == ConflictMode.MERGE


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
            category_conflict_modes={GrammarCategory.AFFIXES: ConflictMode.MERGE},
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
        plan = self._make_plan(0)
        assert plan.selection.conflict_mode_for(GrammarCategory.AFFIXES) == ConflictMode.MERGE
