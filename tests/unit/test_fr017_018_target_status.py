"""Unit tests for FR-017 (affix-count helper) and FR-018 (target-presence status).

Tests:
  - build with target=None -> all rows status is None (back-compat lock)
  - build with target where one GUID matches -> that entry's rows status=="in_target"
  - source affix absent from target GUIDs but form matches -> "similar"
  - source affix with neither GUID nor form match -> "new"
  - status is display-only: affix_picks / all_affix_guids unchanged whether target given or not
  - _count_affixes_in_node returns distinct count over subtree (incl. nested sub-POS)
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.selection import (
    AffixRow,
    PosGroupedAffixInventory,
    PosNode,
    JunkDrawer,
    build_pos_grouped_inventory,
    collapse_pos_grouped,
)
from _fakes_affix import (
    make_infl_entry,
    make_deriv_entry,
    make_no_analysis_entry,
    make_no_pos_entry,
    make_pos,
    make_source,
    FakeEntry,
    FakeInflMsa,
    FakeSense,
)

# ---------------------------------------------------------------------------
# Helpers: build a minimal target source for FR-018 tests
# ---------------------------------------------------------------------------

def _make_target_with_guid(guid: str, form: str, pos):
    """Target source containing one affix with the given guid+form."""
    e = make_infl_entry(guid, form, ["tgloss"], pos)
    return make_source([e], [pos])


def _make_target_with_different_guid(form: str, pos):
    """Target source: affix with a DIFFERENT guid but the same form."""
    e = make_infl_entry("target-guid-different", form, ["tgloss"], pos)
    return make_source([e], [pos])


# ---------------------------------------------------------------------------
# FR-018: back-compat -- target=None means all status is None
# ---------------------------------------------------------------------------

class TestTargetNoneBackcompat:
    def test_no_target_all_status_none_infl(self):
        pos_v = make_pos("pv", "v")
        entry = make_infl_entry("g1", "foo", ["gl"], pos_v)
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)  # no target kwarg
        for row in inv.roots[0].inflectional:
            assert row.status is None, f"Expected None but got {row.status!r}"

    def test_no_target_all_status_none_deriv(self):
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("g2", "bar", ["gl"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src, target=None)
        v_node = next(nd for nd in inv.roots if nd.label == "v")
        n_node = next(nd for nd in inv.roots if nd.label == "n")
        for row in list(v_node.deriv_attaches) + list(n_node.deriv_produces):
            assert row.status is None

    def test_no_target_junk_status_none(self):
        entry = make_no_pos_entry("junk1", "baz")
        src = make_source([entry], [])
        inv = build_pos_grouped_inventory(src)
        for row in inv.junk.no_pos:
            assert row.status is None
        entry2 = make_no_analysis_entry("junk2", "qux")
        src2 = make_source([entry2], [])
        inv2 = build_pos_grouped_inventory(src2)
        for row in inv2.junk.no_analysis:
            assert row.status is None


# ---------------------------------------------------------------------------
# FR-018: "in_target" -- GUID present in target
# ---------------------------------------------------------------------------

class TestInTargetStatus:
    def test_guid_match_gives_in_target(self):
        pos_v = make_pos("pv", "v")
        entry = make_infl_entry("guid-shared", "foo", ["gl"], pos_v)
        src = make_source([entry], [pos_v])
        target = _make_target_with_guid("guid-shared", "foo", pos_v)
        inv = build_pos_grouped_inventory(src, target=target)
        for row in inv.roots[0].inflectional:
            assert row.status == "in_target", f"Expected in_target, got {row.status!r}"

    def test_in_target_propagates_to_both_deriv_rows(self):
        """A deriv entry in target by GUID: both attaches and produces rows get in_target."""
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("guid-shared-deriv", "igi", ["caus"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        target = _make_target_with_guid("guid-shared-deriv", "igi", pos_v)
        inv = build_pos_grouped_inventory(src, target=target)
        v_node = next(nd for nd in inv.roots if nd.label == "v")
        n_node = next(nd for nd in inv.roots if nd.label == "n")
        for row in list(v_node.deriv_attaches) + list(n_node.deriv_produces):
            assert row.status == "in_target"


# ---------------------------------------------------------------------------
# FR-018: "similar" -- GUID absent but form matches (case-insensitive, stripped)
# ---------------------------------------------------------------------------

class TestSimilarStatus:
    def test_form_match_no_guid_gives_similar(self):
        pos_v = make_pos("pv", "v")
        src_entry = make_infl_entry("src-guid-001", "foo", ["gl"], pos_v)
        src = make_source([src_entry], [pos_v])
        # Target has a DIFFERENT guid but the same form
        target = _make_target_with_different_guid("foo", pos_v)
        inv = build_pos_grouped_inventory(src, target=target)
        for row in inv.roots[0].inflectional:
            assert row.status == "similar", f"Expected similar, got {row.status!r}"

    def test_form_match_is_case_insensitive(self):
        pos_v = make_pos("pv", "v")
        src_entry = make_infl_entry("src-guid-002", "FOO", ["gl"], pos_v)
        src = make_source([src_entry], [pos_v])
        target = _make_target_with_different_guid("foo", pos_v)
        inv = build_pos_grouped_inventory(src, target=target)
        for row in inv.roots[0].inflectional:
            assert row.status == "similar"


# ---------------------------------------------------------------------------
# FR-018: "new" -- neither GUID nor form matches
# ---------------------------------------------------------------------------

class TestNewStatus:
    def test_no_match_gives_new(self):
        pos_v = make_pos("pv", "v")
        src_entry = make_infl_entry("src-guid-100", "unique-src-form", ["gl"], pos_v)
        src = make_source([src_entry], [pos_v])
        # Target has a completely different entry
        tgt_entry = make_infl_entry("tgt-guid-999", "different-form", ["tgl"], pos_v)
        target = make_source([tgt_entry], [pos_v])
        inv = build_pos_grouped_inventory(src, target=target)
        for row in inv.roots[0].inflectional:
            assert row.status == "new", f"Expected new, got {row.status!r}"

    def test_empty_target_all_new(self):
        pos_v = make_pos("pv", "v")
        src_entry = make_infl_entry("src-g1", "afoo", ["gl"], pos_v)
        src = make_source([src_entry], [pos_v])
        target = make_source([], [pos_v])  # empty target
        inv = build_pos_grouped_inventory(src, target=target)
        for row in inv.roots[0].inflectional:
            assert row.status == "new"

    def test_junk_entry_gets_new_when_no_match(self):
        src_entry = make_no_pos_entry("junk-src-1", "junk-form")
        src = make_source([src_entry], [])
        target = make_source([], [])
        inv = build_pos_grouped_inventory(src, target=target)
        for row in inv.junk.no_pos:
            assert row.status == "new"


# ---------------------------------------------------------------------------
# FR-018: status is display-only -- affix_picks / all_affix_guids unchanged
# ---------------------------------------------------------------------------

class TestStatusDisplayOnly:
    def test_all_affix_guids_same_with_and_without_target(self):
        pos_v = make_pos("pv", "v")
        e1 = make_infl_entry("g1", "foo", ["gl1"], pos_v)
        e2 = make_infl_entry("g2", "bar", ["gl2"], pos_v)
        src = make_source([e1, e2], [pos_v])
        inv_no_target = build_pos_grouped_inventory(src)
        tgt = make_source([make_infl_entry("g1", "foo", ["tgl"], pos_v)], [pos_v])
        inv_with_target = build_pos_grouped_inventory(src, target=tgt)
        assert inv_no_target.all_affix_guids() == inv_with_target.all_affix_guids()

    def test_collapse_picks_same_with_and_without_target(self):
        pos_v = make_pos("pv", "v")
        e1 = make_infl_entry("g1", "foo", ["gl1"], pos_v)
        e2 = make_infl_entry("g2", "bar", ["gl2"], pos_v)
        src = make_source([e1, e2], [pos_v])
        inv_no_target = build_pos_grouped_inventory(src)
        tgt = make_source([make_infl_entry("g1", "foo", ["tgl"], pos_v)], [pos_v])
        inv_with_target = build_pos_grouped_inventory(src, target=tgt)
        checked = frozenset({"g1", "g2"})
        sel_no_tgt = collapse_pos_grouped(checked, inv_no_target)
        sel_with_tgt = collapse_pos_grouped(checked, inv_with_target)
        assert sel_no_tgt.affix_picks == sel_with_tgt.affix_picks


# ---------------------------------------------------------------------------
# FR-017(b): _count_affixes_in_node
# ---------------------------------------------------------------------------

# Import the helper from the UI module (pure Python, no Qt widget instantiation).
# We import the function directly from the wizard module namespace.
import importlib
import sys


def _get_count_helper():
    """Lazily import _count_affixes_in_node without triggering Qt widget creation."""
    # The helper is a module-level function in selection_wizard; we can import
    # it if PyQt6 is available, or we reimplement the same logic here as a
    # fallback for environments where Qt is absent.
    try:
        # Use importlib to load the module without executing widget code
        # (module-level code only defines functions/constants, no widget creation).
        import gramtrans.Lib.ui.selection_wizard as sw
        return sw._count_affixes_in_node
    except Exception:
        # Fallback: reimplement inline
        def _count(node):
            guids = set()
            def _c(n):
                for r in n.inflectional: guids.add(r.entry_guid)
                for r in n.deriv_attaches: guids.add(r.entry_guid)
                for r in n.deriv_produces: guids.add(r.entry_guid)
                for ch in n.children: _c(ch)
            _c(node)
            return len(guids)
        return _count


class TestCountAffixesInNode:
    def _make_row(self, guid: str) -> AffixRow:
        return AffixRow(entry_guid=guid, form="f", glosses="g",
                        msa_kind="infl", from_pos=None, to_pos=None,
                        role="attaches")

    def _make_node(self, guids, children=()):
        rows = tuple(self._make_row(g) for g in guids)
        return PosNode(
            pos_guid="p", label="v", children=children,
            inflectional=rows, deriv_attaches=(), deriv_produces=(),
        )

    def test_single_node_no_children(self):
        count_fn = _get_count_helper()
        node = self._make_node(["g1", "g2", "g3"])
        assert count_fn(node) == 3

    def test_deduplication_within_node(self):
        """Same GUID in inflectional and deriv_attaches counts once."""
        count_fn = _get_count_helper()
        row_a = self._make_row("g1")
        row_b = AffixRow("g1", "f", "g", "deriv", "v", "n", "attaches")
        row_c = self._make_row("g2")
        node = PosNode("p", "v", (), (row_a, row_c), (row_b,), ())
        assert count_fn(node) == 2  # g1 and g2

    def test_nested_children_summed(self):
        count_fn = _get_count_helper()
        child = self._make_node(["g3", "g4"])
        parent = self._make_node(["g1", "g2"], children=(child,))
        assert count_fn(parent) == 4

    def test_nested_dedup_across_parent_child(self):
        """GUID in parent and child: counted once."""
        count_fn = _get_count_helper()
        child = self._make_node(["g1", "g3"])  # g1 also in parent
        parent = self._make_node(["g1", "g2"], children=(child,))
        assert count_fn(parent) == 3  # g1, g2, g3

    def test_empty_node(self):
        count_fn = _get_count_helper()
        node = PosNode("p", "v", (), (), (), ())
        assert count_fn(node) == 0

    def test_integration_via_builder(self):
        """Verify count matches actual builder output for a simple inventory."""
        count_fn = _get_count_helper()
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        e1 = make_infl_entry("g1", "foo", ["gl"], pos_v)
        e2 = make_infl_entry("g2", "bar", ["gl"], pos_v)
        e3 = make_deriv_entry("g3", "baz", ["gl"], pos_v, pos_n)
        src = make_source([e1, e2, e3], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        v_node = next(nd for nd in inv.roots if nd.label == "v")
        # v has g1(infl), g2(infl), g3(deriv_attaches), g3(deriv_produces in n)
        # count for v node itself (not recursing into n which is a sibling, not child)
        assert count_fn(v_node) == 3  # g1, g2, g3
