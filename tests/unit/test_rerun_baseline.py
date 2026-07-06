"""022-disposition-model T028: Unit tests for re-run baseline (3-way field identity).

SC-006: On re-run with unchanged source, settled fields auto-SKIP (3-way).
        First transfer uses 2-way only, no "untouched" claim.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.conflict import ItemDisposition, compute_disposition, compute_field_diff
from gramtrans.Lib.models import ConflictMode


class TestComputeFieldDiff:
    def test_identical_props_empty_diff(self):
        props = {"Name": "X", "Abbrev": "x"}
        assert compute_field_diff(props, props.copy()) == {}

    def test_one_diverged_field(self):
        src = {"Name": "New", "Abbrev": "x"}
        tgt = {"Name": "Old", "Abbrev": "x"}
        diff = compute_field_diff(src, tgt)
        assert set(diff.keys()) == {"Name"}
        assert diff["Name"] == ("New", "Old")

    def test_non_dict_input_returns_empty(self):
        assert compute_field_diff(None, {}) == {}
        assert compute_field_diff({}, None) == {}


class TestRerunBaseline:
    """(a) prior baseline + unchanged source -> 3-way SKIP (T020)."""

    def test_prior_baseline_unchanged_source_yields_skip(self):
        """Exact SC-006 scenario: transfer, change nothing, re-run -> SKIP."""
        baseline = {"Name": "Noun", "Abbrev": "N"}
        src = {"Name": "Noun", "Abbrev": "N"}  # unchanged since baseline
        tgt = {"Name": "Noun", "Abbrev": "N"}  # target also unchanged
        disp = compute_disposition(
            src_props=src,
            tgt_props=tgt,
            intent=ConflictMode.UPDATE,
            prior_baseline=baseline,
        )
        assert disp == ItemDisposition.SKIP

    def test_target_drifted_from_baseline_surfaces_field(self):
        """Target edited since prior run -> NOT auto-SKIP (baseline drift)."""
        baseline = {"Name": "Noun", "Abbrev": "N"}
        src = {"Name": "Noun", "Abbrev": "N"}  # source unchanged
        tgt = {"Name": "Noun", "Abbrev": "Nn"}  # target changed
        disp = compute_disposition(
            src_props=src,
            tgt_props=tgt,
            intent=ConflictMode.UPDATE,
            prior_baseline=baseline,
        )
        # tgt != baseline => target drifted; not auto-SKIP (src==tgt trivially false here)
        # Since src != tgt on Abbrev (N vs Nn) the field IS diverged on 2-way too.
        assert disp == ItemDisposition.UPDATE

    """(b) no prior baseline -> 2-way only, no "untouched" label (T022)."""

    def test_no_baseline_first_run_identical_is_skip(self):
        """First run, no baseline: identical -> SKIP (2-way)."""
        props = {"Name": "Verb"}
        disp = compute_disposition(
            src_props=props.copy(),
            tgt_props=props.copy(),
            intent=ConflictMode.UPDATE,
            prior_baseline=None,
        )
        assert disp == ItemDisposition.SKIP

    def test_no_baseline_first_run_diverged_is_update(self):
        """First run, no baseline: diverged -> UPDATE (2-way, not claimed 'untouched')."""
        disp = compute_disposition(
            src_props={"Name": "New"},
            tgt_props={"Name": "Old"},
            intent=ConflictMode.UPDATE,
            prior_baseline=None,
        )
        assert disp == ItemDisposition.UPDATE

    """(c) source changed since baseline -> surfaced for re-evaluation (T020)."""

    def test_source_field_changed_since_baseline_surfaced(self):
        """Source changed -> field is diverged, surfaced for re-evaluation."""
        baseline = {"Name": "Old"}
        src = {"Name": "Changed"}  # source changed since baseline
        tgt = {"Name": "Old"}      # target same as baseline
        disp = compute_disposition(
            src_props=src,
            tgt_props=tgt,
            intent=ConflictMode.UPDATE,
            prior_baseline=baseline,
        )
        # src != tgt, AND src != baseline -> surfaced (UPDATE disposition)
        assert disp == ItemDisposition.UPDATE

    def test_source_unchanged_target_unchanged_baseline_match_skip(self):
        """Source and target unchanged since baseline -> both match baseline -> SKIP."""
        baseline = {"Name": "Stable"}
        src = {"Name": "Stable"}
        tgt = {"Name": "Stable"}
        disp = compute_disposition(
            src_props=src,
            tgt_props=tgt,
            intent=ConflictMode.OVERWRITE,  # even OVERWRITE: no diff -> SKIP
            prior_baseline=baseline,
        )
        assert disp == ItemDisposition.SKIP
