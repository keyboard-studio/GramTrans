"""Tests for build_deps_inventory (T004).

TDD: these tests are written BEFORE the implementation in selection.py.
Covers:
  - features/classes/stem-names/exception-features derived from picked
    affixes' POSes, all preselected.
  - empty collections render without error.
  - target-status per row.
"""
from __future__ import annotations

import pytest

from _fakes_affix import (
    make_infl_entry_with_slots,
    make_pos_with_slots,
    make_slot,
    make_source,
    FakeInflFeature,
    FakeInflClass,
    FakeStemName,
)

from gramtrans.Lib.selection import build_deps_inventory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_deps_scene():
    """POS with one infl feature, one class, and one stem name."""
    feat = FakeInflFeature("feat-1", "Tense")
    cls = FakeInflClass("cls-1", "Class1")
    sn = FakeStemName("sn-1", "StemA")
    slot = make_slot("slot-1", "Present")
    pos_v = make_pos_with_slots(
        "pv", "v", "Verb", slots=[slot],
        infl_feats=[feat], infl_classes=[cls],
        stem_names=[sn],
    )
    entry = make_infl_entry_with_slots("e1", "-s", ["3sg"], pos_v, [slot])
    source = make_source([entry], [pos_v])
    affix_picks = frozenset(["e1"])
    return source, affix_picks, feat, cls, sn


# ---------------------------------------------------------------------------
# T004: basic deps derivation
# ---------------------------------------------------------------------------

class TestBuildDepsInventoryBasic:

    def test_returns_result(self):
        source, affix_picks, feat, cls, sn = _make_deps_scene()
        result = build_deps_inventory(source, affix_picks)
        assert result is not None

    def test_infl_features_present_and_preselected(self):
        source, affix_picks, feat, cls, sn = _make_deps_scene()
        result = build_deps_inventory(source, affix_picks)
        guids = [r.guid for r in result.infl_features]
        assert "feat-1" in guids
        for row in result.infl_features:
            assert row.preselected is True

    def test_infl_classes_present_and_preselected(self):
        source, affix_picks, feat, cls, sn = _make_deps_scene()
        result = build_deps_inventory(source, affix_picks)
        guids = [r.guid for r in result.infl_classes]
        assert "cls-1" in guids
        for row in result.infl_classes:
            assert row.preselected is True

    def test_stem_names_present_and_preselected(self):
        source, affix_picks, feat, cls, sn = _make_deps_scene()
        result = build_deps_inventory(source, affix_picks)
        guids = [r.guid for r in result.stem_names]
        assert "sn-1" in guids
        for row in result.stem_names:
            assert row.preselected is True

    def test_empty_infl_classes_no_error(self):
        slot = make_slot("sl", "S")
        pos_v = make_pos_with_slots("pv", "v", "V", slots=[slot])
        entry = make_infl_entry_with_slots("e1", "-s", ["g"], pos_v, [slot])
        source = make_source([entry], [pos_v])
        result = build_deps_inventory(source, frozenset(["e1"]))
        assert result.infl_classes == []

    def test_empty_stem_names_no_error(self):
        slot = make_slot("sl", "S")
        pos_v = make_pos_with_slots("pv", "v", "V", slots=[slot])
        entry = make_infl_entry_with_slots("e1", "-s", ["g"], pos_v, [slot])
        source = make_source([entry], [pos_v])
        result = build_deps_inventory(source, frozenset(["e1"]))
        assert result.stem_names == []

    def test_no_target_status_none_when_no_target(self):
        source, affix_picks, feat, cls, sn = _make_deps_scene()
        result = build_deps_inventory(source, affix_picks)
        for row in result.infl_features + result.infl_classes + result.stem_names:
            assert row.status is None

    def test_only_attaching_pos_deps_included(self):
        """A POS that no picked affix attaches to should NOT contribute deps."""
        feat_v = FakeInflFeature("feat-v", "Tense")
        feat_n = FakeInflFeature("feat-n", "Number")
        slot_v = make_slot("sv", "V-slot")
        slot_n = make_slot("sn", "N-slot")
        pos_v = make_pos_with_slots("pv", "v", "Verb", slots=[slot_v],
                                     infl_feats=[feat_v])
        pos_n = make_pos_with_slots("pn", "n", "Noun", slots=[slot_n],
                                     infl_feats=[feat_n])
        e_v = make_infl_entry_with_slots("e1", "-s", ["g"], pos_v, [slot_v])
        e_n = make_infl_entry_with_slots("e2", "-pl", ["g"], pos_n, [slot_n])
        source = make_source([e_v, e_n], [pos_v, pos_n])
        # Only pick the verb affix
        result = build_deps_inventory(source, frozenset(["e1"]))
        guids = [r.guid for r in result.infl_features]
        assert "feat-v" in guids
        assert "feat-n" not in guids

    def test_deduplication_across_pos(self):
        """A feature shared by two POSes should appear only once."""
        feat = FakeInflFeature("feat-shared", "Shared")
        slot_v = make_slot("sv", "V")
        slot_n = make_slot("sn", "N")
        pos_v = make_pos_with_slots("pv", "v", "V", slots=[slot_v], infl_feats=[feat])
        pos_n = make_pos_with_slots("pn", "n", "N", slots=[slot_n], infl_feats=[feat])
        e1 = make_infl_entry_with_slots("e1", "-s", ["g"], pos_v, [slot_v])
        e2 = make_infl_entry_with_slots("e2", "-pl", ["g"], pos_n, [slot_n])
        source = make_source([e1, e2], [pos_v, pos_n])
        result = build_deps_inventory(source, frozenset(["e1", "e2"]))
        assert len([r for r in result.infl_features if r.guid == "feat-shared"]) == 1


# ---------------------------------------------------------------------------
# FR-009: SELF-TARGET deps status (all rows must read "in_target")
# ---------------------------------------------------------------------------

class TestDepsSelfTargetStatus:
    """When target==source project every deps row must read 'in_target'.

    This is the exact case the pre-fix cycle missed: the old code looked up
    dep-object GUIDs against the affix-entry set, so features/classes/stem-
    names/exception-features (which are not affix entries) all fell to "new".
    The fix enumerates per-kind GUID sets from the target's POS hierarchy.
    """

    def _self_target_scene(self):
        feat = FakeInflFeature("feat-1", "Tense")
        cls = FakeInflClass("cls-1", "Class1")
        sn = FakeStemName("sn-1", "StemA")
        slot = make_slot("slot-1", "Present")
        pos_v = make_pos_with_slots(
            "pv", "v", "Verb", slots=[slot],
            infl_feats=[feat], infl_classes=[cls],
            stem_names=[sn],
        )
        entry = make_infl_entry_with_slots("e1", "-s", ["3sg"], pos_v, [slot])
        handle = make_source([entry], [pos_v])
        affix_picks = frozenset(["e1"])
        return handle, affix_picks

    def test_infl_feature_in_target_for_self_target(self):
        handle, picks = self._self_target_scene()
        result = build_deps_inventory(handle, picks, target=handle)
        for row in result.infl_features:
            assert row.status == "in_target", (
                f"feat {row.guid} status={row.status!r}"
            )

    def test_infl_class_in_target_for_self_target(self):
        handle, picks = self._self_target_scene()
        result = build_deps_inventory(handle, picks, target=handle)
        for row in result.infl_classes:
            assert row.status == "in_target", (
                f"class {row.guid} status={row.status!r}"
            )

    def test_stem_name_in_target_for_self_target(self):
        handle, picks = self._self_target_scene()
        result = build_deps_inventory(handle, picks, target=handle)
        for row in result.stem_names:
            assert row.status == "in_target", (
                f"stem {row.guid} status={row.status!r}"
            )

    def test_all_deps_rows_in_target_for_self_target(self):
        """Parametric: every dep row of every kind must be 'in_target'."""
        handle, picks = self._self_target_scene()
        result = build_deps_inventory(handle, picks, target=handle)
        all_rows = (
            result.infl_features + result.infl_classes + result.stem_names
        )
        assert len(all_rows) == 3, "Expected one row per dep kind (3 kinds)"
        for row in all_rows:
            assert row.status == "in_target", (
                f"dep {row.guid} ({row.label}) status={row.status!r}"
            )

    def test_dep_absent_from_target_shows_new(self):
        """A dep GUID absent from the target's POS hierarchy must read 'new'."""
        feat_src = FakeInflFeature("feat-src", "Tense-src")
        slot_src = make_slot("slot-src", "Src")
        pos_src = make_pos_with_slots(
            "pos-src", "v", "Verb", slots=[slot_src], infl_feats=[feat_src]
        )
        entry_src = make_infl_entry_with_slots("e-src", "-s", ["g"], pos_src, [slot_src])
        source = make_source([entry_src], [pos_src])

        # Target has a completely different feature GUID
        feat_tgt = FakeInflFeature("feat-tgt", "Tense-tgt")
        slot_tgt = make_slot("slot-tgt", "Tgt")
        pos_tgt = make_pos_with_slots(
            "pos-tgt", "n", "Noun", slots=[slot_tgt], infl_feats=[feat_tgt]
        )
        entry_tgt = make_infl_entry_with_slots("e-tgt", "-pl", ["g"], pos_tgt, [slot_tgt])
        target = make_source([entry_tgt], [pos_tgt])

        result = build_deps_inventory(source, frozenset(["e-src"]), target=target)
        assert len(result.infl_features) == 1
        assert result.infl_features[0].status == "new"
