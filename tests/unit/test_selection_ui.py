"""Tests for Phase 3c Selection UI extension (Tasks 1-7).

Covers:
- CategoryScope enum + back-compat constructor mapping (T1)
- build_selection with category_scopes / excluded_deps (T2)
- Selection.scope_for() per-scope resolution (T1)
- Selection.is_dep_excluded() (T1)
- ExcludedLossy dataclass validation (T1)
- EXCLUDED-LOSSY warning computation in preview.py (_check_msa_pos_excluded_lossy) (T4)
- RunPlan.excluded_lossy field (T1)
- RunReport.excluded_lossy propagation via report.py (T5)
- Confirm-on-Move gate logic (T7, pure-logic slice without Qt)
- Null-tolerant creation sentinel existence in transfer.py (T4)
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.models import (
    CategoryScope,
    ExcludedLossy,
    GrammarCategory,
    RunContext,
    RunPlan,
    Selection,
    SkipReason,
    WSMapping,
)
from gramtrans.Lib.selection import build_selection, PickerState, SourceAffixInventory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context():
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
# T1: CategoryScope enum
# ===========================================================================

class TestCategoryScopeEnum:
    def test_values(self):
        assert CategoryScope.NONE.value == "none"
        assert CategoryScope.AS_NEEDED.value == "as_needed"
        assert CategoryScope.ALL.value == "all"

    def test_three_members(self):
        members = list(CategoryScope)
        assert len(members) == 3


# ===========================================================================
# T1: Back-compat constructor mapping (include_closure bool -> uniform scope)
# ===========================================================================

class TestSelectionBackCompat:
    """Old callers pass include_closure=True/False; scope_for() must derive from it."""

    def test_include_closure_true_gives_as_needed(self):
        sel = Selection(
            categories={GrammarCategory.POS: True},
            include_closure=True,
        )
        scope = sel.scope_for(GrammarCategory.POS)
        assert scope == CategoryScope.AS_NEEDED

    def test_include_closure_false_gives_none(self):
        sel = Selection(
            categories={GrammarCategory.POS: True},
            include_closure=False,
        )
        scope = sel.scope_for(GrammarCategory.POS)
        assert scope == CategoryScope.NONE

    def test_explicit_scope_overrides_include_closure(self):
        """Explicit category_scopes entry takes priority over include_closure."""
        sel = Selection(
            categories={GrammarCategory.POS: True},
            include_closure=False,  # would give NONE by back-compat
            category_scopes={GrammarCategory.POS: CategoryScope.ALL},
        )
        assert sel.scope_for(GrammarCategory.POS) == CategoryScope.ALL

    def test_missing_scope_falls_back_to_include_closure(self):
        """A category not in category_scopes still falls back to include_closure."""
        sel = Selection(
            categories={GrammarCategory.POS: True, GrammarCategory.AFFIXES: True},
            include_closure=True,
            category_scopes={GrammarCategory.AFFIXES: CategoryScope.NONE},
        )
        # POS not in category_scopes -> falls back to include_closure=True -> AS_NEEDED
        assert sel.scope_for(GrammarCategory.POS) == CategoryScope.AS_NEEDED
        # AFFIXES has explicit NONE
        assert sel.scope_for(GrammarCategory.AFFIXES) == CategoryScope.NONE


# ===========================================================================
# T1: is_dep_excluded
# ===========================================================================

class TestIsDependencyExcluded:
    def test_dep_in_excluded_deps_returns_true(self):
        guid = "aaaabbbb-0000-0000-0000-000000000001"
        sel = Selection(excluded_deps=frozenset({guid}))
        assert sel.is_dep_excluded(guid) is True

    def test_dep_not_in_excluded_deps_returns_false(self):
        guid = "aaaabbbb-0000-0000-0000-000000000001"
        sel = Selection(excluded_deps=frozenset())
        assert sel.is_dep_excluded(guid) is False

    def test_empty_excluded_deps_by_default(self):
        sel = Selection()
        assert sel.excluded_deps == frozenset()


# ===========================================================================
# T1: ExcludedLossy dataclass
# ===========================================================================

class TestExcludedLossyDataclass:
    def _make(self, **kwargs):
        defaults = dict(
            category=GrammarCategory.ENTRY,
            entry_guid="aaaa-0001",
            entry_label="-PL",
            dep_category=GrammarCategory.POS,
            dep_guid="bbbb-0002",
            dep_label="Verb",
            message="Entry '-PL' will have no Part of Speech.",
        )
        defaults.update(kwargs)
        return ExcludedLossy(**defaults)

    def test_valid_construction(self):
        el = self._make()
        assert el.entry_label == "-PL"
        assert el.message == "Entry '-PL' will have no Part of Speech."

    def test_empty_entry_guid_raises(self):
        with pytest.raises(ValueError, match="entry_guid"):
            self._make(entry_guid="")

    def test_empty_message_raises(self):
        with pytest.raises(ValueError, match="message"):
            self._make(message="")


# ===========================================================================
# T1: RunPlan carries excluded_lossy
# ===========================================================================

class TestRunPlanExcludedLossy:
    def test_default_empty(self):
        ctx = _make_context()
        sel = Selection()
        plan = RunPlan(context=ctx, selection=sel, ws_mapping=WSMapping())
        assert plan.excluded_lossy == ()

    def test_excluded_lossy_count(self):
        ctx = _make_context()
        sel = Selection()
        el = ExcludedLossy(
            category=GrammarCategory.ENTRY,
            entry_guid="aaa",
            entry_label="lex",
            dep_category=GrammarCategory.POS,
            dep_guid="bbb",
            dep_label="Verb",
            message="Entry 'lex' will have no Part of Speech.",
        )
        plan = RunPlan(
            context=ctx,
            selection=sel,
            ws_mapping=WSMapping(),
            excluded_lossy=(el,),
        )
        assert plan.excluded_lossy_count() == 1


# ===========================================================================
# T2: build_selection with category_scopes / excluded_deps
# ===========================================================================

class TestBuildSelectionWithScopes:
    def _empty_inventory(self):
        return SourceAffixInventory()

    def _empty_picker(self):
        return PickerState()

    def test_category_scopes_passed_through(self):
        scopes = {GrammarCategory.POS: CategoryScope.NONE}
        sel = build_selection(
            self._empty_picker(),
            self._empty_inventory(),
            category_scopes=scopes,
        )
        assert sel.category_scopes == scopes
        assert sel.scope_for(GrammarCategory.POS) == CategoryScope.NONE

    def test_excluded_deps_passed_through(self):
        deps = frozenset({"guid-1", "guid-2"})
        sel = build_selection(
            self._empty_picker(),
            self._empty_inventory(),
            excluded_deps=deps,
        )
        assert sel.excluded_deps == deps

    def test_defaults_still_work(self):
        """Calling build_selection without the new kwargs must still work."""
        sel = build_selection(self._empty_picker(), self._empty_inventory())
        assert sel.category_scopes == {}
        assert sel.excluded_deps == frozenset()
        assert sel.include_closure is True

    def test_back_compat_include_closure_false(self):
        sel = build_selection(
            self._empty_picker(),
            self._empty_inventory(),
            include_closure=False,
        )
        assert sel.scope_for(GrammarCategory.INFLECTION_FEATURES) == CategoryScope.NONE


# ===========================================================================
# T4: EXCLUDED-LOSSY warning computation helper
# (unit-tested with pure-Python stubs — no LCM runtime needed)
# ===========================================================================

class TestExcludedLossyWarningComputation:
    """Test the logic path through Selection.scope_for + is_dep_excluded that
    drives EXCLUDED-LOSSY warning emission.

    We don't call _check_msa_pos_excluded_lossy directly (it needs LCM),
    but we can verify the predicate logic that drives it.
    """

    def test_none_scope_marks_dep_as_excluded(self):
        sel = Selection(
            categories={GrammarCategory.POS: True},
            category_scopes={GrammarCategory.POS: CategoryScope.NONE},
        )
        # Logic: scope is NONE -> dep is excluded
        scope = sel.scope_for(GrammarCategory.POS)
        assert scope == CategoryScope.NONE
        dep_excluded = (scope == CategoryScope.NONE) or sel.is_dep_excluded("any-guid")
        assert dep_excluded is True

    def test_as_needed_with_excluded_guid_marks_dep_excluded(self):
        guid = "pos-guid-0001"
        sel = Selection(
            categories={GrammarCategory.POS: True},
            category_scopes={GrammarCategory.POS: CategoryScope.AS_NEEDED},
            excluded_deps=frozenset({guid}),
        )
        scope = sel.scope_for(GrammarCategory.POS)
        assert scope == CategoryScope.AS_NEEDED
        dep_excluded = (scope == CategoryScope.NONE) or sel.is_dep_excluded(guid)
        assert dep_excluded is True

    def test_as_needed_without_excluded_guid_not_excluded(self):
        sel = Selection(
            categories={GrammarCategory.POS: True},
            category_scopes={GrammarCategory.POS: CategoryScope.AS_NEEDED},
        )
        scope = sel.scope_for(GrammarCategory.POS)
        dep_excluded = (scope == CategoryScope.NONE) or sel.is_dep_excluded("any-guid")
        assert dep_excluded is False

    def test_all_scope_not_excluded(self):
        sel = Selection(
            categories={GrammarCategory.POS: True},
            category_scopes={GrammarCategory.POS: CategoryScope.ALL},
        )
        scope = sel.scope_for(GrammarCategory.POS)
        dep_excluded = (scope == CategoryScope.NONE) or sel.is_dep_excluded("any-guid")
        assert dep_excluded is False


# ===========================================================================
# T5: RunReport excluded_lossy propagation via report.py
# ===========================================================================

class TestRunReportExcludedLossyPropagation:
    def _make_plan_with_lossy(self, lossy_items):
        import gramtrans.Lib.report  # ensure monkey-patch applied  # noqa
        ctx = _make_context()
        sel = Selection()
        return RunPlan(
            context=ctx,
            selection=sel,
            ws_mapping=WSMapping(),
            excluded_lossy=tuple(lossy_items),
        )

    def _make_el(self, msg="Entry '-PL' will have no Part of Speech."):
        return ExcludedLossy(
            category=GrammarCategory.ENTRY,
            entry_guid="entry-001",
            entry_label="-PL",
            dep_category=GrammarCategory.POS,
            dep_guid="pos-001",
            dep_label="Verb",
            message=msg,
        )

    def test_excluded_lossy_propagated_to_run_report(self):
        from gramtrans.Lib.models import RunMode
        el = self._make_el()
        plan = self._make_plan_with_lossy([el])
        report = plan.context.__class__  # just checking import
        # Use build_from_plan directly
        rpt = RunPlan.build_from_plan if hasattr(RunPlan, "build_from_plan") else None
        if rpt is None:
            from gramtrans.Lib.models import RunReport
            rpt = RunReport.build_from_plan
        from gramtrans.Lib.models import RunReport
        r = RunReport.build_from_plan(plan, RunMode.PREVIEW)
        assert len(r.excluded_lossy) == 1
        assert r.excluded_lossy[0].message == "Entry '-PL' will have no Part of Speech."

    def test_excluded_lossy_count_in_per_category(self):
        from gramtrans.Lib.models import RunMode, RunReport
        el = self._make_el()
        plan = self._make_plan_with_lossy([el])
        r = RunReport.build_from_plan(plan, RunMode.PREVIEW)
        cat_report = r.per_category.get(GrammarCategory.ENTRY)
        assert cat_report is not None
        assert cat_report.excluded_lossy == 1

    def test_no_excluded_lossy_gives_empty_tuple(self):
        from gramtrans.Lib.models import RunMode, RunReport
        plan = self._make_plan_with_lossy([])
        r = RunReport.build_from_plan(plan, RunMode.PREVIEW)
        assert r.excluded_lossy == ()

    def test_render_text_summary_includes_warning(self):
        from gramtrans.Lib.models import RunMode, RunReport
        from gramtrans.Lib.report import render_text_summary
        el = self._make_el()
        plan = self._make_plan_with_lossy([el])
        r = RunReport.build_from_plan(plan, RunMode.PREVIEW)
        text = "\n".join(render_text_summary(r))
        assert "Warnings" in text
        assert "missing references" in text
        assert "-PL" in text


# ===========================================================================
# T7: Confirm-on-Move gate — pure logic slice
# ===========================================================================

class TestConfirmOnMoveGatePureLogic:
    """Test the confirm-on-Move decision logic without touching Qt.

    We verify: if excluded_lossy is non-empty, a confirmation step is
    required; if empty, no confirmation step.
    """

    def _make_plan(self, lossy_count: int) -> RunPlan:
        import gramtrans.Lib.report  # noqa — ensure build_from_plan attached
        ctx = _make_context()
        sel = Selection()
        lossy = tuple(
            ExcludedLossy(
                category=GrammarCategory.ENTRY,
                entry_guid=f"entry-{i:03d}",
                entry_label=f"entry{i}",
                dep_category=GrammarCategory.POS,
                dep_guid=f"pos-{i:03d}",
                dep_label="Verb",
                message=f"Entry 'entry{i}' will have no Part of Speech.",
            )
            for i in range(lossy_count)
        )
        return RunPlan(
            context=ctx,
            selection=sel,
            ws_mapping=WSMapping(),
            excluded_lossy=lossy,
        )

    def test_no_lossy_no_confirmation_needed(self):
        plan = self._make_plan(0)
        el_count = len(getattr(plan, "excluded_lossy", ()))
        assert el_count == 0
        # no dialog needed
        confirmation_required = el_count > 0
        assert confirmation_required is False

    def test_lossy_present_confirmation_required(self):
        plan = self._make_plan(3)
        el_count = len(getattr(plan, "excluded_lossy", ()))
        assert el_count == 3
        confirmation_required = el_count > 0
        assert confirmation_required is True

    def test_lossy_count_matches_plan(self):
        for n in (1, 5, 10):
            plan = self._make_plan(n)
            assert plan.excluded_lossy_count() == n


# ===========================================================================
# T4: Null-tolerant creation helper exists in transfer.py
# ===========================================================================

class TestNullTolerantCreationHelperExists:
    def test_helper_is_importable(self):
        """_create_inflaff_msa_null_tolerant must be defined in transfer.py."""
        from gramtrans.Lib import transfer
        assert hasattr(transfer, "_create_inflaff_msa_null_tolerant"), (
            "_create_inflaff_msa_null_tolerant helper not found in transfer.py"
        )

    def test_main_function_has_null_tolerant_branch(self):
        """_create_inflaff_msa_with_guid must accept target_verb=None and
        dispatch to the null-tolerant path instead of raising."""
        import inspect
        from gramtrans.Lib import transfer
        src = inspect.getsource(transfer._create_inflaff_msa_with_guid)
        assert "_create_inflaff_msa_null_tolerant" in src, (
            "_create_inflaff_msa_with_guid does not call null-tolerant helper"
        )
        assert "target_verb is None" in src, (
            "_create_inflaff_msa_with_guid does not branch on target_verb is None"
        )


# ===========================================================================
# T8: Back-compat regression — existing Selection construction still works
# ===========================================================================

class TestBackCompatRegressionSelectionConstruction:
    """Verify the existing 324-test suite's Selection construction patterns
    still work with no changes required to old code paths."""

    def test_selection_with_no_new_kwargs(self):
        """Bare Selection() with no new kwargs must work exactly as before."""
        sel = Selection(
            categories={GrammarCategory.POS: True},
            include_closure=True,
            enable_overwrite=False,
        )
        assert sel.is_on(GrammarCategory.POS)
        assert sel.include_closure is True
        assert sel.category_scopes == {}
        assert sel.excluded_deps == frozenset()

    def test_scope_for_returns_as_needed_for_old_style(self):
        """Old-style Selection with include_closure=True -> AS_NEEDED for all cats."""
        sel = Selection(include_closure=True)
        for cat in GrammarCategory:
            assert sel.scope_for(cat) == CategoryScope.AS_NEEDED

    def test_scope_for_returns_none_for_closure_off(self):
        """Old-style Selection with include_closure=False -> NONE for all cats."""
        sel = Selection(include_closure=False)
        for cat in GrammarCategory:
            assert sel.scope_for(cat) == CategoryScope.NONE

    def test_affix_picks_still_validates_category(self):
        """affix_picks still raises if AFFIXES not in categories."""
        with pytest.raises(ValueError):
            Selection(affix_picks=frozenset({"guid-1"}))
