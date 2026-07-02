"""Run-report aggregation and snapshot-JSON serialization.

Implements `RunReport.to_snapshot_json()` per contracts/run-report.md. The
output JSON has stable field ordering so integration-test snapshot diffs are
meaningful.

Per constitution Principle III closing clause + FR-018, every PlannedAction
in the run plan must end up in either `per_category[*].added` or `skips` —
nothing disappears silently. The FR-018 invariant is enforced by
`RunReport.__post_init__` at construction time.
"""
from __future__ import annotations

import json
from typing import Iterable

if __package__:
    from .models import (
        CategoryReport,
        ExcludedLossy,
        GrammarCategory,
        PlannedAction,
        RunMode,
        RunPlan,
        RunReport,
        Skip,
        SkipReason,
    )
else:
    from models import (
        CategoryReport,
        ExcludedLossy,
        GrammarCategory,
        PlannedAction,
        RunMode,
        RunPlan,
        RunReport,
        Skip,
        SkipReason,
    )


# ============================================================================
# RunReport factory + methods (monkey-patched onto the frozen dataclass)
# ============================================================================
# We attach these as classmethods / methods on RunReport here rather than in
# models.py so models.py stays free of JSON / serialization concerns.

def _build_from_plan(cls, plan: RunPlan, mode: RunMode,
                     wall_clock_seconds: float = 0.0,
                     extra_skips=(),
                     extra_excluded_lossy=()) -> RunReport:
    """Build a finalized RunReport from a RunPlan.

    Iterates plan.actions to accumulate per-category added/closure_pulled_in
    counts, then iterates plan.skips to accumulate per-category skipped counts
    and the aggregate skips tuple. Returns a RunReport whose FR-018 invariant
    (checked in __post_init__) will pass because the counts are built from the
    same plan.
    """
    per_category: dict = {}

    def _bucket(cat):
        if cat not in per_category:
            per_category[cat] = {
                "added": 0, "skipped": 0, "closure_pulled_in": 0, "overwritten": 0,
                "interactive_resolved": 0, "interactive_skipped": 0,
                "ws_mapped": 0, "ws_created": 0, "ws_skipped": 0,
                "excluded_lossy": 0,
            }
        return per_category[cat]

    for action in plan.actions:
        b = _bucket(action.category)
        b["added"] += 1
        if action.pulled_in_by:
            b["closure_pulled_in"] += 1

    skips_list: list = []
    for skip in plan.skips:
        b = _bucket(skip.category)
        b["skipped"] += 1
        skips_list.append(skip)

    # Phase 1 (FR-110): count overwrites per category. Tolerate plans
    # produced before Phase 1 (no `overwrites` attribute) by falling back
    # to an empty tuple.
    for ow in getattr(plan, "overwrites", ()):
        b = _bucket(ow.category)
        b["overwritten"] += 1
        if getattr(ow, "pulled_in_by", ()):
            b["closure_pulled_in"] += 1

    # Phase 2 (T030): account for INTERACTIVE_SKIP records emitted by
    # _apply_merge_decisions during execute().  These are not in
    # plan.skips (the plan was built before any user input) so they
    # flow in via the `extra_skips` parameter.
    for skip in extra_skips:
        b = _bucket(skip.category)
        b["skipped"] += 1
        skips_list.append(skip)
        if skip.reason == SkipReason.INTERACTIVE_SKIP:
            b["interactive_skipped"] += 1

    # Phase 3c Selection UI: tally EXCLUDED-LOSSY warnings from the plan
    # and any extras passed in by the executor.
    excluded_lossy_all: list = list(getattr(plan, "excluded_lossy", ()))
    excluded_lossy_all.extend(extra_excluded_lossy)
    for el in excluded_lossy_all:
        b = _bucket(el.category)
        b["excluded_lossy"] += 1

    per_category_final = {
        cat: CategoryReport(
            added=counts["added"],
            skipped=counts["skipped"],
            closure_pulled_in=counts["closure_pulled_in"],
            overwritten=counts["overwritten"],
            interactive_resolved=counts["interactive_resolved"],
            interactive_skipped=counts["interactive_skipped"],
            ws_mapped=counts["ws_mapped"],
            ws_created=counts["ws_created"],
            ws_skipped=counts["ws_skipped"],
            excluded_lossy=counts["excluded_lossy"],
        )
        for cat, counts in per_category.items()
    }

    # Phase 3a FR-308: categories selected by the user but with zero
    # items in source are surfaced as "empty_categories" so
    # render_text_summary can emit "[skip] no items in source for X".
    selected_cats = {
        c for c, on in getattr(plan, "selection", None).categories.items() if on
    } if getattr(plan, "selection", None) is not None else set()
    empty_cats = tuple(sorted(
        (c for c in selected_cats if c not in per_category_final),
        key=lambda c: c.value,
    ))

    return cls(
        context=plan.context,
        mode=mode,
        per_category=per_category_final,
        skips=tuple(skips_list),
        identity_remap=dict(plan.identity_remap),
        wall_clock_seconds=wall_clock_seconds,
        empty_categories=empty_cats,
        excluded_lossy=tuple(excluded_lossy_all),
    )


def _to_snapshot_json(self) -> str:
    """Render a RunReport as a deterministic JSON string for snapshot diffing.

    per_category keys are enum NAMES (e.g. "AFFIXES") ordered by
    GrammarCategory enum declaration order.
    """
    # Order per_category by GrammarCategory enum declaration order
    ordered_members = list(GrammarCategory.__members__)  # declaration order
    ordered_cats = [
        GrammarCategory[name]
        for name in ordered_members
        if GrammarCategory[name] in self.per_category
    ]

    payload = {
        "mode": self.mode.name,
        "context": {
            "run_id": self.context.run_id,
            "source_project_name": self.context.source_project_name,
            "target_project_name": self.context.target_project_name,
            "started_at": self.context.started_at,
        },
        "per_category": {
            cat.name: {
                "added": self.per_category[cat].added,
                "skipped": self.per_category[cat].skipped,
                "closure_pulled_in": self.per_category[cat].closure_pulled_in,
                "overwritten": getattr(self.per_category[cat], "overwritten", 0),
            }
            for cat in ordered_cats
        },
        "skips": [
            {
                "category": s.category.name,
                "source_guid": s.source_guid,
                "reason": s.reason.name,
                "detail": s.detail,
            }
            for s in self.skips
        ],
        "identity_remap": dict(sorted(self.identity_remap.items())),
        "wall_clock_seconds": round(self.wall_clock_seconds, 3),
    }
    return json.dumps(payload, indent=2, sort_keys=False)


# Attach as methods on RunReport (dataclass is frozen but method attachment works)
RunReport.build_from_plan = classmethod(_build_from_plan)
RunReport.to_snapshot_json = _to_snapshot_json


# ============================================================================
# Thin shim for callers that used the old module-level function
# ============================================================================

def to_snapshot_json(r: RunReport) -> str:
    """Shim: delegates to RunReport.to_snapshot_json() so preview.py /
    transfer.py callers don't break while they are updated."""
    return r.to_snapshot_json()


# ============================================================================
# Console rendering (for the FlexTools report.Info pane)
# ============================================================================

def render_text_summary(report: RunReport) -> Iterable[str]:
    """Yield human-readable summary lines for the FlexTools report pane.

    Used by gramtrans.py.MainFunction in both Preview and Move modes until
    the PyQt stats panel (T056/T066) replaces it.
    """
    yield f"[GramTrans] Run report  mode={report.mode.value}  run_id={report.context.run_id}"
    yield f"  Source: {report.context.source_project_name!r}"
    yield f"  Target: {report.context.target_project_name!r}"
    total_added = 0
    total_skipped = 0
    total_overwritten = 0
    for cat in sorted(report.per_category.keys(), key=lambda c: c.value):
        r = report.per_category[cat]
        total_added += r.added
        total_skipped += r.skipped
        ow = getattr(r, "overwritten", 0)
        total_overwritten += ow
        suffix = (
            f"  added={r.added}  skipped={r.skipped}"
            + (f"  overwritten={ow}" if ow else "")
            + (f"  pulled_in={r.closure_pulled_in}" if r.closure_pulled_in else "")
        )
        yield f"  {cat.value:18s}{suffix}"
    yield (
        f"  {'TOTAL':18s}  added={total_added}  skipped={total_skipped}"
        + (f"  overwritten={total_overwritten}" if total_overwritten else "")
    )
    # Phase 3a FR-308: surface selected-but-empty categories explicitly so
    # the linguist sees the scan happened even when nothing transferred.
    for cat in getattr(report, "empty_categories", ()):
        yield f"  [skip] no items in source for {cat.value}"
    if report.skips:
        yield "  Skips:"
        for s in report.skips:
            yield f"    - [{s.category.value}] {s.source_guid}  {s.reason.value}: {s.detail}"
    if getattr(report, "excluded_lossy", ()):
        yield f"  Warnings (entries with missing references) -- {len(report.excluded_lossy)} total:"
        for el in report.excluded_lossy:
            yield f"    - [WARN] {el.message}"
    if report.identity_remap:
        yield "  Identity remap (LCM denied GUID-on-create):"
        for src, dst in sorted(report.identity_remap.items()):
            yield f"    - {src} -> {dst}"
    yield f"  Wall clock: {report.wall_clock_seconds:.3f}s"
