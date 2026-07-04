"""Phase 3b T011: leaf-dispatch wiring smoke for the 9 Phase 3b categories.

Confirms `build_run_plan` threads each of the 9 Phase 3b categories
through the `_LEAF_DISPATCH_CATEGORIES` loop when the category is in
the selection -- including the 5 COMPLETE Phase 0 callbacks
(gram_categories, inflection_features, inflection_classes, stem_names,
exception_features) which Phase 3b is wiring through leaf dispatch for
the first time.

Strategy: drive `build_run_plan` against a FakeProject whose every
Operations accessor returns an empty list. The expected outcome is a
RunPlan with zero actions and zero skips, and -- via FR-308 inherited
from Phase 3a -- 9 `empty_categories` entries in the resulting
RunReport.

The 4 stub categories (custom_fields, variant_types,
complex_form_types, semantic_domains) currently raise
NotImplementedError from enumerate_source -- the dispatch loop catches
those via the FR-308 errors-as-skips path and treats them as empty.
This test pins that behaviour so we notice if a future change removes
the safety net.
"""
from __future__ import annotations

from gramtrans.Lib import preview, report as report_mod
from gramtrans.Lib.models import (
    GrammarCategory,
    RunContext,
    RunMode,
    Selection,
    WSMapping,
)


# ============================================================================
# Fakes
# ============================================================================

class _EmptyOps:
    def GetAll(self, recursive=True):
        return []


class _EmptyProject:
    """FakeProject whose every flexicon Operations accessor returns []."""

    # Phase 3a/3b accessors used by the leaf-dispatch enumerate callbacks.
    GramCat = _EmptyOps()
    InflectionFeatures = _EmptyOps()
    POS = _EmptyOps()
    Strata = _EmptyOps()
    Phonemes = _EmptyOps()
    PhonFeatures = _EmptyOps()
    NaturalClasses = _EmptyOps()
    Environments = _EmptyOps()
    PhonRules = _EmptyOps()

    def ProjectName(self):
        return "EmptyFake"


def _ctx() -> RunContext:
    src = _EmptyProject()
    tgt = _EmptyProject()
    return RunContext(
        source_handle=src, source_project_name="Src", source_project_path="/s",
        target_handle=tgt, target_project_name="Tgt", target_project_path="/t",
        run_id="GT-PHASE3B-DISPATCH", started_at="2026-06-21T02:00:00",
    )


_PHASE3B_CATS = (
    GrammarCategory.GRAM_CATEGORIES,
    GrammarCategory.INFLECTION_FEATURES,
    GrammarCategory.CUSTOM_FIELDS,
    GrammarCategory.INFLECTION_CLASSES,
    GrammarCategory.STEM_NAMES,
    GrammarCategory.EXCEPTION_FEATURES,
    GrammarCategory.VARIANT_TYPES,
    GrammarCategory.COMPLEX_FORM_TYPES,
    GrammarCategory.SEMANTIC_DOMAINS,
)


# ============================================================================
# Tests
# ============================================================================

def test_dispatch_loop_handles_all_9_phase3b_categories_empty_source() -> None:
    """All 9 Phase 3b categories ticked, every source accessor empty:
    build_run_plan returns a plan with zero actions and zero skips."""
    ctx = _ctx()
    selection = Selection(categories={c: True for c in _PHASE3B_CATS})
    plan = preview.build_run_plan(
        ctx, selection, WSMapping(entries=()), ctx.source_handle, ctx.target_handle
    )
    assert plan.actions == ()
    assert plan.skips == ()
    assert plan.overwrites == ()


def test_dispatch_loop_emits_empty_category_lines_via_fr308() -> None:
    """FR-308 inherited from Phase 3a: when source is empty for all
    9 Phase 3b categories, the RunReport carries 9 empty_categories
    entries that render_text_summary surfaces as `[skip] no items in
    source for X` lines."""
    ctx = _ctx()
    selection = Selection(categories={c: True for c in _PHASE3B_CATS})
    plan = preview.build_run_plan(
        ctx, selection, WSMapping(entries=()), ctx.source_handle, ctx.target_handle
    )
    rpt = report_mod.RunReport.build_from_plan(plan, RunMode.PREVIEW)
    empty_cat_values = {c.value for c in rpt.empty_categories}
    for cat in _PHASE3B_CATS:
        assert cat.value in empty_cat_values, (
            f"FR-308: {cat.value} should appear in empty_categories "
            f"because source has no items"
        )


def test_each_phase3b_category_registers_a_callback_bundle() -> None:
    """Spec contract: every Phase 3b category has 5 callbacks in
    LEAF_CATEGORIES, keyed under its GrammarCategory member."""
    from gramtrans.Lib import categories
    expected_keys = {"enumerate_source", "dependencies",
                     "required_writing_systems", "plan_action",
                     "execute_action"}
    for cat in _PHASE3B_CATS:
        bundle = categories.for_category(cat)
        assert set(bundle.keys()) == expected_keys, (
            f"{cat.value} bundle is missing one or more callbacks"
        )


def test_dispatch_tuple_includes_all_9_phase3b_categories() -> None:
    """preview.py and transfer.py must agree on the leaf-dispatch
    contents (the spec's contract is that they're identical)."""
    import inspect
    src_preview = inspect.getsource(preview.build_run_plan)
    from gramtrans.Lib import transfer
    src_transfer = inspect.getsource(transfer.execute)
    for cat in _PHASE3B_CATS:
        assert f"GrammarCategory.{cat.name}" in src_preview, (
            f"preview.py dispatch tuple missing {cat.name}"
        )
        assert f"GrammarCategory.{cat.name}" in src_transfer, (
            f"transfer.py dispatch tuple missing {cat.name}"
        )
