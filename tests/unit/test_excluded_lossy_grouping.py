"""Tests for EXCLUDED-LOSSY aggregation helper (T005).

Verifies:
  - N deselected-needed-absent items -> N entry warnings but ONE consolidated
    gate payload.
  - Items present in target -> no warning (LINK).
  - Pure function, no LCM/Qt required.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.selection import build_excluded_lossy_warnings


class TestExcludedLossyAggregation:
    """Test the EXCLUDED-LOSSY aggregation helper."""

    def _make_items(self, n_items: int, in_target: bool = False):
        """Make n_items deselected items for slot deps.

        Returns (affix_picks_needing_slot, deselected_slot_guids, target_slot_guids).
        """
        # Each item: one affix that fills one slot; slot is deselected
        affix_slot_map = {}  # affix_guid -> [slot_guid]
        slot_guids = set()
        for i in range(n_items):
            affix_guid = f"affix-{i}"
            slot_guid = f"slot-{i}"
            affix_slot_map[affix_guid] = [slot_guid]
            slot_guids.add(slot_guid)

        target_slot_guids = slot_guids if in_target else set()
        return affix_slot_map, slot_guids, target_slot_guids

    def test_n_deselected_absent_yields_n_warnings(self):
        affix_slot_map, deselected, target = self._make_items(3, in_target=False)
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids=deselected,
            target_slot_guids=target,
        )
        assert len(warnings) == 3

    def test_items_in_target_no_warning(self):
        """Deselected items that ARE in the target -> LINK, no warning."""
        affix_slot_map, deselected, target = self._make_items(3, in_target=True)
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids=deselected,
            target_slot_guids=target,
        )
        assert len(warnings) == 0

    def test_mixed_in_target_and_absent(self):
        """2 absent + 1 in-target -> 2 warnings (not 3)."""
        affix_slot_map = {
            "affix-0": ["slot-0"],
            "affix-1": ["slot-1"],
            "affix-2": ["slot-2"],
        }
        deselected = {"slot-0", "slot-1", "slot-2"}
        target = {"slot-2"}  # slot-2 is in target -> LINK
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids=deselected,
            target_slot_guids=target,
        )
        assert len(warnings) == 2

    def test_gate_payload_is_consolidated(self):
        """N warnings all count toward a SINGLE aggregated count."""
        affix_slot_map, deselected, target = self._make_items(5, in_target=False)
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids=deselected,
            target_slot_guids=target,
        )
        # All 5 warnings are returned as a single list (the dialog shows the count)
        assert len(warnings) == 5
        # Each warning has entry_guid and message
        for w in warnings:
            assert hasattr(w, "entry_guid")
            assert hasattr(w, "message")
            assert w.message

    def test_zero_deselected_no_warnings(self):
        """Empty deselected set -> no warnings."""
        affix_slot_map = {"affix-0": ["slot-0"]}
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids=set(),
            target_slot_guids=set(),
        )
        assert len(warnings) == 0

    def test_affix_not_needing_deselected_slot_no_warning(self):
        """Affix doesn't fill the deselected slot -> no warning for it."""
        # affix-0 fills slot-X; slot-0 is deselected but affix-0 doesn't fill it
        affix_slot_map = {"affix-0": ["slot-x"]}
        deselected = {"slot-0"}
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids=deselected,
            target_slot_guids=set(),
        )
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# FR-010/011: deselected POS omission warnings
# ---------------------------------------------------------------------------

class TestExcludedLossyPosOmissions:
    """Deselected POS that an affix attaches to and that is absent from target
    must generate an EXCLUDED-LOSSY warning."""

    def test_deselected_pos_absent_from_target_yields_warning(self):
        affix_pos_map = {"affix-a": "pos-1"}
        warnings = build_excluded_lossy_warnings(
            affix_slot_map={},
            deselected_slot_guids=set(),
            target_slot_guids=set(),
            deselected_pos_guids={"pos-1"},
            target_pos_guids=set(),
            affix_pos_map=affix_pos_map,
        )
        assert len(warnings) == 1
        w = warnings[0]
        assert w.entry_guid == "affix-a"
        assert w.dep_guid == "pos-1"
        assert "Part of Speech" in w.message or "POS" in w.message

    def test_deselected_pos_in_target_no_warning(self):
        """POS absent from selection but present in target is a LINK -> no warning."""
        affix_pos_map = {"affix-a": "pos-1"}
        warnings = build_excluded_lossy_warnings(
            affix_slot_map={},
            deselected_slot_guids=set(),
            target_slot_guids=set(),
            deselected_pos_guids={"pos-1"},
            target_pos_guids={"pos-1"},
            affix_pos_map=affix_pos_map,
        )
        assert len(warnings) == 0

    def test_multiple_affixes_deselected_pos_yields_one_warning_each(self):
        """Two affixes needing the same deselected POS -> two warnings."""
        affix_pos_map = {"affix-a": "pos-1", "affix-b": "pos-1"}
        warnings = build_excluded_lossy_warnings(
            affix_slot_map={},
            deselected_slot_guids=set(),
            target_slot_guids=set(),
            deselected_pos_guids={"pos-1"},
            target_pos_guids=set(),
            affix_pos_map=affix_pos_map,
        )
        assert len(warnings) == 2

    def test_slot_and_pos_warnings_consolidated_in_one_list(self):
        """Slot omissions + POS omissions all land in the SAME returned list."""
        affix_slot_map = {"affix-a": ["slot-1"]}
        affix_pos_map = {"affix-b": "pos-1"}
        warnings = build_excluded_lossy_warnings(
            affix_slot_map=affix_slot_map,
            deselected_slot_guids={"slot-1"},
            target_slot_guids=set(),
            deselected_pos_guids={"pos-1"},
            target_pos_guids=set(),
            affix_pos_map=affix_pos_map,
        )
        assert len(warnings) == 2
        entry_guids = {w.entry_guid for w in warnings}
        assert "affix-a" in entry_guids
        assert "affix-b" in entry_guids


# ---------------------------------------------------------------------------
# FR-010/011: deselected deps omission warnings
# ---------------------------------------------------------------------------

class TestExcludedLossyDepsOmissions:
    """Deselected dep (feature/class/stem-name/exception-feat) that a kept affix
    needs and that is absent from target must generate an EXCLUDED-LOSSY warning."""

    def _make_deps_args(self, dep_guid="dep-1", absent=True, n_affixes=1):
        """Build keyword args for build_excluded_lossy_warnings for a deps case."""
        from gramtrans.Lib.models import GrammarCategory
        deps_by_affix = {
            f"affix-{i}": {dep_guid: []} for i in range(n_affixes)
        }
        target_dep_guids = set() if absent else {dep_guid}
        return dict(
            affix_slot_map={},
            deselected_slot_guids=set(),
            target_slot_guids=set(),
            deps_by_affix=deps_by_affix,
            deselected_dep_guids={dep_guid},
            target_dep_guids=target_dep_guids,
            dep_labels={dep_guid: "Tense"},
            dep_category=GrammarCategory.INFLECTION_FEATURES,
        )

    def test_deselected_dep_absent_yields_warning(self):
        from gramtrans.Lib.selection import build_excluded_lossy_warnings
        warnings = build_excluded_lossy_warnings(**self._make_deps_args(absent=True))
        assert len(warnings) == 1
        w = warnings[0]
        assert w.dep_guid == "dep-1"
        assert "Tense" in w.message

    def test_deselected_dep_in_target_no_warning(self):
        from gramtrans.Lib.selection import build_excluded_lossy_warnings
        warnings = build_excluded_lossy_warnings(**self._make_deps_args(absent=False))
        assert len(warnings) == 0

    def test_multiple_affixes_needing_same_dep_each_warns(self):
        from gramtrans.Lib.selection import build_excluded_lossy_warnings
        warnings = build_excluded_lossy_warnings(
            **self._make_deps_args(absent=True, n_affixes=3)
        )
        assert len(warnings) == 3

    def test_slot_pos_deps_all_consolidated(self):
        """Slot + POS + dep omissions all land in one list (single Move dialog)."""
        from gramtrans.Lib.selection import build_excluded_lossy_warnings
        from gramtrans.Lib.models import GrammarCategory
        warnings = build_excluded_lossy_warnings(
            affix_slot_map={"affix-a": ["slot-1"]},
            deselected_slot_guids={"slot-1"},
            target_slot_guids=set(),
            deselected_pos_guids={"pos-1"},
            target_pos_guids=set(),
            affix_pos_map={"affix-b": "pos-1"},
            deps_by_affix={"affix-c": {"dep-1": []}},
            deselected_dep_guids={"dep-1"},
            target_dep_guids=set(),
            dep_labels={"dep-1": "Tense"},
            dep_category=GrammarCategory.INFLECTION_FEATURES,
        )
        assert len(warnings) == 3
        cats = {w.dep_category for w in warnings}
        assert GrammarCategory.SLOTS in cats
        assert GrammarCategory.POS in cats
        assert GrammarCategory.INFLECTION_FEATURES in cats
