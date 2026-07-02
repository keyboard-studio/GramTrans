"""T018: Move-gate payload aggregation unit test.

Verifies that all EXCLUDED-LOSSY omissions are aggregated into a SINGLE
count — never one dialog per item (FR-011, US5).

Tests the pure build_excluded_lossy_warnings helper directly.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.selection import build_excluded_lossy_warnings


class TestMoveGateAggregation:
    """Test EXCLUDED-LOSSY aggregation for the Move-gate dialog."""

    def test_all_omissions_yield_single_list(self):
        """N omissions -> one list returned; the dialog shows len(list) as one total."""
        affix_slot_map = {
            "affix-0": ["slot-0"],
            "affix-1": ["slot-1"],
            "affix-2": ["slot-2"],
        }
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids={"slot-0", "slot-1", "slot-2"},
            target_slot_guids=set(),
        )
        # All 3 warnings in a single list -> count = 3
        assert len(warnings) == 3

    def test_single_dialog_semantics_count(self):
        """The gate shows one dialog with sum(warnings) — never one per affix."""
        affix_slot_map = {f"a{i}": [f"s{i}"] for i in range(10)}
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids={f"s{i}" for i in range(10)},
            target_slot_guids=set(),
        )
        # There are 10 warnings; a single dialog shows "10 entries will transfer…"
        assert len(warnings) == 10
        # The caller uses len(warnings) as the dialog's count — one dialog total.

    def test_no_warnings_no_dialog(self):
        """When no omissions exist, the count is 0 -> no dialog shown."""
        warnings = build_excluded_lossy_warnings(
            affix_slot_map={"a0": ["s0"]},
            deselected_slot_guids=set(),
            target_slot_guids=set(),
        )
        assert len(warnings) == 0

    def test_target_present_reduces_count(self):
        """Items already in target are LINK (no warning); only absent items count."""
        affix_slot_map = {"a0": ["s0"], "a1": ["s1"], "a2": ["s2"]}
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids={"s0", "s1", "s2"},
            target_slot_guids={"s1"},  # s1 in target -> LINK
        )
        assert len(warnings) == 2

    def test_each_warning_has_entry_guid_and_message(self):
        """Each ExcludedLossy in the list must have non-empty entry_guid and message."""
        affix_slot_map = {"affix-x": ["slot-x"]}
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids={"slot-x"},
            target_slot_guids=set(),
        )
        assert len(warnings) == 1
        w = warnings[0]
        assert w.entry_guid == "affix-x"
        assert w.message
        assert "affix-x" in w.message or "slot-x" in w.message
