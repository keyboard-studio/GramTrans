"""T063: FR-018 no-silent-drops invariant.

Every PlannedAction in the plan MUST end up either as a +1 added in some
CategoryReport OR as an entry in the report's skips list — never silently
absent. Same for every plan Skip. The `RunReport.__post_init__` invariant
gives us this by construction; this test exercises the property end-to-end
with a fabricated multi-category plan.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.models import (
    GrammarCategory,
    PlannedAction,
    RunContext,
    RunMode,
    RunPlan,
    Selection,
    Skip,
    SkipReason,
    WSMapping,
)
from gramtrans.Lib.report import RunReport


def _ctx() -> RunContext:
    return RunContext(
        source_handle=object(),
        source_project_name="Src",
        source_project_path="/src",
        target_handle=object(),
        target_project_name="Tgt",
        target_project_path="/tgt",
        run_id="GT-20260619-150000",
        started_at="2026-06-19T15:00:00",
    )


def _action(cat: GrammarCategory, guid: str, *, pulled_in: bool = False) -> PlannedAction:
    return PlannedAction(
        category=cat,
        source_guid=guid,
        intended_target_guid=guid,
        summary=f"add {cat.name} {guid}",
        pulled_in_by=("parent",) if pulled_in else (),
    )


def _skip(cat: GrammarCategory, guid: str, reason: SkipReason = SkipReason.UNMAPPED_WS) -> Skip:
    return Skip(
        category=cat,
        source_guid=guid,
        reason=reason,
        detail=f"skip {guid}: {reason.value}",
    )


def _plan(actions, skips) -> RunPlan:
    return RunPlan(
        context=_ctx(),
        selection=Selection(categories={GrammarCategory.AFFIXES: True}),
        ws_mapping=WSMapping(entries=()),
        actions=tuple(actions),
        skips=tuple(skips),
    )


def test_every_action_lands_in_added_count() -> None:
    """N actions + 0 skips → sum of added across categories == N."""
    plan = _plan(
        actions=[
            _action(GrammarCategory.AFFIXES, "a1"),
            _action(GrammarCategory.AFFIXES, "a2"),
            _action(GrammarCategory.AFFIX_TEMPLATES, "t1"),
            _action(GrammarCategory.SLOTS, "s1", pulled_in=True),
            _action(GrammarCategory.SLOTS, "s2", pulled_in=True),
        ],
        skips=[],
    )
    report = RunReport.build_from_plan(plan, RunMode.MOVE)
    total_added = sum(r.added for r in report.per_category.values())
    assert total_added == 5
    assert report.per_category[GrammarCategory.AFFIXES].added == 2
    assert report.per_category[GrammarCategory.AFFIX_TEMPLATES].added == 1
    assert report.per_category[GrammarCategory.SLOTS].added == 2


def test_every_skip_lands_in_skipped_count_and_skips_list() -> None:
    """0 actions + M skips → sum of skipped == M and len(skips) == M."""
    plan = _plan(
        actions=[],
        skips=[
            _skip(GrammarCategory.AFFIXES, "a3", SkipReason.UNMAPPED_WS),
            _skip(GrammarCategory.AFFIX_TEMPLATES, "t9", SkipReason.GOLD_INVIOLABLE),
            _skip(GrammarCategory.SLOTS, "s9", SkipReason.DEPENDENCY_UNRESOLVED),
        ],
    )
    report = RunReport.build_from_plan(plan, RunMode.PREVIEW)
    total_skipped = sum(r.skipped for r in report.per_category.values())
    assert total_skipped == 3
    assert len(report.skips) == 3


def test_mixed_actions_and_skips_account_for_n_plus_m() -> None:
    """N actions + M skips → total accounted == N + M, no silent drops."""
    actions = [
        _action(GrammarCategory.AFFIXES, f"a{i}", pulled_in=(i % 2 == 0))
        for i in range(7)
    ]
    skips = [
        _skip(GrammarCategory.AFFIXES, f"sa{i}") for i in range(3)
    ] + [
        _skip(GrammarCategory.AFFIX_TEMPLATES, "st1", SkipReason.GOLD_INVIOLABLE),
    ]
    plan = _plan(actions=actions, skips=skips)
    report = RunReport.build_from_plan(plan, RunMode.MOVE)
    total = sum(r.added + r.skipped for r in report.per_category.values())
    assert total == len(actions) + len(skips)
    assert len(report.skips) == len(skips)


def test_closure_pulled_in_count_separate_from_total_added() -> None:
    """closure_pulled_in is a SUBCOUNT of added (not a separate bucket)."""
    plan = _plan(
        actions=[
            _action(GrammarCategory.AFFIXES, "a1", pulled_in=False),  # user-picked
            _action(GrammarCategory.AFFIXES, "a2", pulled_in=True),   # pulled in
            _action(GrammarCategory.AFFIXES, "a3", pulled_in=True),   # pulled in
        ],
        skips=[],
    )
    report = RunReport.build_from_plan(plan, RunMode.MOVE)
    aff = report.per_category[GrammarCategory.AFFIXES]
    assert aff.added == 3
    assert aff.closure_pulled_in == 2
    # closure_pulled_in <= added (subcount, not in addition to)
    assert aff.closure_pulled_in <= aff.added


def test_empty_plan_yields_empty_report() -> None:
    plan = _plan(actions=[], skips=[])
    report = RunReport.build_from_plan(plan, RunMode.PREVIEW)
    assert report.per_category == {}
    assert report.skips == ()
    assert report.total_added() if hasattr(report, "total_added") else sum(
        r.added for r in report.per_category.values()
    ) == 0


def test_construction_with_inconsistent_skipped_raises_fr018() -> None:
    """Direct dataclass construction with hand-crafted mismatched counts MUST
    raise FR-018. The factory wouldn't produce this, but we double-check the
    `__post_init__` guardrail."""
    from gramtrans.Lib.models import CategoryReport
    with pytest.raises(ValueError, match="FR-018"):
        RunReport(
            context=_ctx(),
            mode=RunMode.MOVE,
            per_category={
                GrammarCategory.AFFIXES: CategoryReport(added=0, skipped=2),
            },
            skips=(_skip(GrammarCategory.AFFIXES, "a1"),),  # only 1 entry vs claim of 2
        )
