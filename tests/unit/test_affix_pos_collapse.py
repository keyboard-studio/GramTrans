"""T006-T007, T017: Unit tests for collapse_pos_grouped and mirror_check_state.

T006: collapse_pos_grouped -> Selection with deduped affix_picks.
T007: mirror_check_state returns correct (item, state) assignments.
T017: picker-state fixture with group-check minus deselected GUID.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.selection import (
    AffixRow,
    JunkDrawer,
    PosGroupedAffixInventory,
    PosNode,
    build_pos_grouped_inventory,
    collapse_pos_grouped,
    mirror_check_state,
)
from gramtrans.Lib.models import GrammarCategory
from _fakes_affix import (
    make_deriv_entry,
    make_infl_entry,
    make_pos,
    make_source,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_row(guid: str, role: str = "attaches") -> AffixRow:
    return AffixRow(
        entry_guid=guid,
        form=guid,
        glosses="gloss",
        msa_kind="infl",
        from_pos=None,
        to_pos=None,
        role=role,
    )


def _make_simple_inventory(guids: list[str]) -> PosGroupedAffixInventory:
    """Build a minimal inventory with inflectional rows under a single POS."""
    rows = tuple(_make_row(g) for g in guids)
    node = PosNode(
        pos_guid="pv",
        label="v",
        children=(),
        inflectional=rows,
        deriv_attaches=(),
        deriv_produces=(),
    )
    return PosGroupedAffixInventory(roots=(node,), junk=JunkDrawer((), ()))


# =============================================================================
# T006 - collapse_pos_grouped tests
# =============================================================================

class TestCollapsePosGrouped:
    def test_checked_guids_become_affix_picks(self):
        inv = _make_simple_inventory(["g1", "g2", "g3"])
        sel = collapse_pos_grouped({"g1", "g2"}, inv)
        assert sel.affix_picks == frozenset({"g1", "g2"})

    def test_template_and_slot_picks_are_empty(self):
        inv = _make_simple_inventory(["g1"])
        sel = collapse_pos_grouped({"g1"}, inv)
        assert sel.template_picks == frozenset()

    def test_unknown_guids_filtered(self):
        inv = _make_simple_inventory(["g1"])
        sel = collapse_pos_grouped({"g1", "ghost"}, inv)
        assert "ghost" not in sel.affix_picks
        assert sel.affix_picks == frozenset({"g1"})

    def test_guid_appearing_in_multiple_groups_deduped(self):
        """An entry in both attaches and produces groups -> one GUID in affix_picks."""
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("multi_guid", "foo", ["gl"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        # Check the guid as found in both appearances
        sel = collapse_pos_grouped({"multi_guid"}, inv)
        assert sel.affix_picks == frozenset({"multi_guid"})

    def test_empty_checked_guids(self):
        inv = _make_simple_inventory(["g1", "g2"])
        sel = collapse_pos_grouped(set(), inv)
        assert sel.affix_picks == frozenset()

    def test_all_guids_checked(self):
        inv = _make_simple_inventory(["g1", "g2", "g3"])
        sel = collapse_pos_grouped({"g1", "g2", "g3"}, inv)
        assert sel.affix_picks == frozenset({"g1", "g2", "g3"})

    def test_affix_picks_populates_affixes_category(self):
        inv = _make_simple_inventory(["g1"])
        sel = collapse_pos_grouped({"g1"}, inv)
        assert sel.categories.get(GrammarCategory.AFFIXES) is True

    def test_empty_picks_no_affixes_category(self):
        inv = _make_simple_inventory(["g1"])
        sel = collapse_pos_grouped(set(), inv)
        assert GrammarCategory.AFFIXES not in sel.categories


# =============================================================================
# T007 - mirror_check_state tests
# =============================================================================

class _FakeTreeItem:
    """Minimal fake for a QTreeWidgetItem with check-state tracking."""
    def __init__(self, guid: str):
        self.guid = guid
        self._state = None

    def __repr__(self):
        return f"FakeTreeItem({self.guid!r}, state={self._state})"


class TestMirrorCheckState:
    def test_all_items_get_new_state(self):
        items = [_FakeTreeItem("g1"), _FakeTreeItem("g1"), _FakeTreeItem("g1")]
        result = mirror_check_state(items, "checked")
        assert len(result) == 3
        for item, state in result:
            assert state == "checked"

    def test_empty_items_returns_empty(self):
        assert mirror_check_state([], "checked") == []

    def test_single_item(self):
        item = _FakeTreeItem("g1")
        result = mirror_check_state([item], "unchecked")
        assert result == [(item, "unchecked")]

    def test_returns_same_item_objects(self):
        items = [_FakeTreeItem("g1"), _FakeTreeItem("g1")]
        result = mirror_check_state(items, "checked")
        returned_items = [i for i, _ in result]
        assert returned_items[0] is items[0]
        assert returned_items[1] is items[1]

    def test_different_states_propagated(self):
        items = [_FakeTreeItem("g1")]
        for state_val in ("checked", "unchecked", "partial"):
            result = mirror_check_state(items, state_val)
            assert result[0][1] == state_val


# =============================================================================
# T017 - Collapse / mirroring wiring at state level
# =============================================================================

class TestCollapseMirroringWiring:
    def test_group_check_minus_deselected(self):
        """Checked set of all verb affixes minus one deselected -> correct picks."""
        pos_v = make_pos("pv", "v")
        e1 = make_infl_entry("g1", "aaa", ["gl1"], pos_v)
        e2 = make_infl_entry("g2", "bbb", ["gl2"], pos_v)
        e3 = make_infl_entry("g3", "ccc", ["gl3"], pos_v)
        src = make_source([e1, e2, e3], [pos_v])
        inv = build_pos_grouped_inventory(src)
        # Simulate group-check all, then deselect g2
        all_guids = {r.entry_guid for r in inv.roots[0].inflectional}
        checked = all_guids - {"g2"}
        sel = collapse_pos_grouped(checked, inv)
        assert sel.affix_picks == frozenset({"g1", "g3"})

    def test_produces_only_guid_excluded_from_header_check(self):
        """A GUID that appears only in deriv_produces is NOT selected by header check."""
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        # deriv entry: from=v, to=n -> attaches to v, produces n
        entry = make_deriv_entry("deriv1", "foo", ["gl"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        # Header check on "n" node would only select n.inflectional + n.deriv_attaches
        # deriv1 is only in n.deriv_produces, so NOT swept
        n_node = next(nd for nd in inv.roots if nd.label == "n")
        header_guids = {r.entry_guid for r in n_node.inflectional}
        header_guids |= {r.entry_guid for r in n_node.deriv_attaches}
        # deriv1 should NOT be in header_guids
        assert "deriv1" not in header_guids
        sel = collapse_pos_grouped(header_guids, inv)
        assert "deriv1" not in sel.affix_picks
