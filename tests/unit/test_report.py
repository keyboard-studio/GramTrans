"""T024: RunReport.to_snapshot_json() field ordering + invariants
(contracts/run-report.md)."""

from __future__ import annotations

import json

import pytest

from gramtrans.Lib.report import CategoryReport, RunReport
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


def _ctx() -> RunContext:
    return RunContext(
        source_handle=object(),
        source_project_name="Ejagham Mini",
        source_project_path=r"C:\fake\Ejagham Mini\Ejagham Mini.fwdata",
        target_handle=object(),
        target_project_name="Ejagham Full",
        target_project_path=r"C:\fake\Ejagham Full\Ejagham Full.fwdata",
        run_id="GT-20260619-140000",
        started_at="2026-06-19T14:00:00",
    )


def _plan(actions: tuple[PlannedAction, ...], skips: tuple[Skip, ...]) -> RunPlan:
    return RunPlan(
        context=_ctx(),
        selection=Selection(
            categories={GrammarCategory.AFFIXES: True},
        ),
        ws_mapping=WSMapping(entries=()),
        actions=actions,
        skips=skips,
    )


def _action(cat: GrammarCategory, guid: str, *, pulled_in: bool = False) -> PlannedAction:
    return PlannedAction(
        category=cat,
        source_guid=guid,
        intended_target_guid=guid,
        summary=f"add {cat.name} {guid}",
        pulled_in_by=("x",) if pulled_in else (),
    )


def _skip(cat: GrammarCategory, guid: str) -> Skip:
    return Skip(
        category=cat,
        source_guid=guid,
        reason=SkipReason.UNMAPPED_WS,
        detail="ws 'seh-fonipa' not mapped",
    )


def test_report_aggregates_counts() -> None:
    plan = _plan(
        actions=(
            _action(GrammarCategory.AFFIXES, "a-1"),
            _action(GrammarCategory.AFFIXES, "a-2", pulled_in=True),
            _action(GrammarCategory.AFFIX_TEMPLATES, "t-1"),
        ),
        skips=(_skip(GrammarCategory.AFFIXES, "a-3"),),
    )
    report = RunReport.build_from_plan(plan, RunMode.MOVE, wall_clock_seconds=1.5)
    assert report.per_category[GrammarCategory.AFFIXES] == CategoryReport(
        added=2, skipped=1, closure_pulled_in=1
    )
    assert report.per_category[GrammarCategory.AFFIX_TEMPLATES] == CategoryReport(added=1)


def test_snapshot_json_is_valid_json_and_orders_categories_by_enum_order() -> None:
    plan = _plan(
        actions=(
            _action(GrammarCategory.AFFIX_TEMPLATES, "t-1"),
            _action(GrammarCategory.AFFIXES, "a-1"),
        ),
        skips=(),
    )
    report = RunReport.build_from_plan(plan, RunMode.PREVIEW)
    snap = report.to_snapshot_json()
    data = json.loads(snap)
    # GrammarCategory enum declares AFFIXES before AFFIX_TEMPLATES; the snapshot
    # MUST honor that order for deterministic diffs.
    cats = list(data["per_category"].keys())
    assert cats.index("AFFIXES") < cats.index("AFFIX_TEMPLATES")
    assert data["mode"] == "PREVIEW"


def test_fr018_invariant_checks_skip_consistency() -> None:
    # Building a RunReport with mismatched per_category.skipped vs len(skips)
    # MUST raise (defensive — caller would have produced this from a bad
    # plan).
    ctx = _ctx()
    with pytest.raises(ValueError, match="FR-018"):
        RunReport(
            context=ctx,
            mode=RunMode.PREVIEW,
            per_category={
                GrammarCategory.AFFIXES: CategoryReport(added=1, skipped=1)
            },
            skips=(),  # claims 1 skip in per_category but 0 in list
        )
