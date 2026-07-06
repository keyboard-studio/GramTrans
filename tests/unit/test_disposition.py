"""022-disposition-model T027: Unit tests for per-item disposition computation.

SC-004: An already-present item with zero field differences is SKIP; an unselected
item is IGNORE. The two are never conflated.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.conflict import ItemDisposition, compute_disposition
from gramtrans.Lib.models import ConflictMode


class TestItemDispositionEnum:
    def test_all_five_values(self):
        values = {d.value for d in ItemDisposition}
        assert values == {"ignore", "skip", "add", "update", "overwrite"}

    def test_ignore_distinct_from_skip(self):
        assert ItemDisposition.IGNORE != ItemDisposition.SKIP

    def test_skip_distinct_from_update(self):
        assert ItemDisposition.SKIP != ItemDisposition.UPDATE


class TestComputeDisposition:
    """(a) all-identical item -> SKIP, no write."""

    def test_all_identical_yields_skip(self):
        props = {"Name": "X", "Abbrev": "x"}
        disp = compute_disposition(props, props.copy(), ConflictMode.UPDATE)
        assert disp == ItemDisposition.SKIP

    def test_all_identical_under_overwrite_yields_skip(self):
        """Even OVERWRITE intent: no diff -> SKIP."""
        props = {"Name": "X"}
        disp = compute_disposition(props, props.copy(), ConflictMode.OVERWRITE)
        assert disp == ItemDisposition.SKIP

    """(b) item not in plan -> IGNORE (caller responsibility, not compute_disposition)."""

    def test_ignore_is_not_computed_here(self):
        """IGNORE is the caller's domain: unselected items never enter the plan.
        compute_disposition returns ADD when tgt_props is None (item absent),
        not IGNORE. Callers must assign IGNORE for unselected items."""
        disp = compute_disposition(
            src_props={"Name": "X"},
            tgt_props=None,
            intent=ConflictMode.UPDATE,
        )
        assert disp == ItemDisposition.ADD  # absent from target -> ADD
        # NOTE: IGNORE must be assigned by callers for unselected items;
        # compute_disposition never produces IGNORE.
        assert ItemDisposition.IGNORE.value == "ignore"

    """(c) >=1 diverged field under UPDATE -> UPDATE disposition, not SKIP."""

    def test_diverged_field_update_not_skip(self):
        src = {"Name": "New", "Abbrev": "N"}
        tgt = {"Name": "Old", "Abbrev": "N"}
        disp = compute_disposition(src, tgt, ConflictMode.UPDATE)
        assert disp == ItemDisposition.UPDATE
        assert disp != ItemDisposition.SKIP

    """3-way baseline tests (US5)."""

    def test_3way_baseline_unchanged_yields_skip(self):
        """Prior baseline + unchanged source + unchanged target -> SKIP."""
        props = {"Name": "X", "Abbrev": "x"}
        # baseline == target (untouched since prior run); src == baseline (no change)
        disp = compute_disposition(
            src_props=props.copy(),
            tgt_props=props.copy(),
            intent=ConflictMode.UPDATE,
            prior_baseline=props.copy(),
        )
        assert disp == ItemDisposition.SKIP

    def test_3way_source_changed_since_baseline_yields_update(self):
        """Source changed since baseline -> still surfaced (not auto-SKIP)."""
        baseline = {"Name": "Old", "Abbrev": "O"}
        src = {"Name": "New", "Abbrev": "O"}  # Name changed since baseline
        tgt = {"Name": "Old", "Abbrev": "O"}  # target same as baseline
        disp = compute_disposition(
            src_props=src,
            tgt_props=tgt,
            intent=ConflictMode.UPDATE,
            prior_baseline=baseline,
        )
        # src != tgt AND src != baseline -> diverged, surfaced
        assert disp == ItemDisposition.UPDATE

    def test_first_run_no_baseline_uses_2way(self):
        """First run (no baseline): 2-way identical-vs-diverged only (T022)."""
        src = {"Name": "New"}
        tgt = {"Name": "Old"}
        disp = compute_disposition(src, tgt, ConflictMode.UPDATE, prior_baseline=None)
        assert disp == ItemDisposition.UPDATE

    def test_first_run_identical_2way_skip(self):
        """First run: identical src and tgt -> SKIP via 2-way."""
        props = {"Name": "Same"}
        disp = compute_disposition(props.copy(), props.copy(), ConflictMode.UPDATE)
        assert disp == ItemDisposition.SKIP
