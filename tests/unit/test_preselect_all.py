"""T010: Preselect-all unit test.

Validates that when the affix picker opens with all affixes preselected
(FR-001), the resulting affix_picks equals all source affix GUIDs.

This test is pure (no Qt); it verifies the builder-level invariant:
build_pos_grouped_inventory().all_affix_guids() == the set that would be
returned by collect_selection() when every affix row is checked.

The Qt-level check (group tristates fully checked) is validated by the live
integration test (T013/T015) and by the UI smoke test (T022).
"""
from __future__ import annotations

import pytest

from _fakes_affix import (
    make_infl_entry,
    make_deriv_entry,
    make_pos,
    make_source,
)
from gramtrans.Lib.selection import (
    build_pos_grouped_inventory,
    collapse_pos_grouped,
)


def test_preselect_all_affixes_collapse_yields_all_guids():
    """Checking all affixes -> collapse yields all source affix GUIDs."""
    pos_v = make_pos("pv", "v")
    pos_n = make_pos("pn", "n")
    e1 = make_infl_entry("e1", "-s", ["3sg"], pos_v)
    e2 = make_infl_entry("e2", "-pl", ["pl"], pos_v)
    e3 = make_infl_entry("e3", "-n", ["N"], pos_n)
    source = make_source([e1, e2, e3], [pos_v, pos_n])
    inventory = build_pos_grouped_inventory(source)
    all_guids = inventory.all_affix_guids()
    assert all_guids == frozenset(["e1", "e2", "e3"])
    # Collapse with all guids checked (simulating preselect-all)
    sel = collapse_pos_grouped(all_guids, inventory)
    assert sel.affix_picks == all_guids


def test_preselect_all_single_deselect():
    """All affixes preselected, then deselect one -> affix_picks = all minus one."""
    pos_v = make_pos("pv", "v")
    e1 = make_infl_entry("e1", "-s", ["3sg"], pos_v)
    e2 = make_infl_entry("e2", "-pl", ["pl"], pos_v)
    e3 = make_infl_entry("e3", "-past", ["past"], pos_v)
    source = make_source([e1, e2, e3], [pos_v])
    inventory = build_pos_grouped_inventory(source)
    all_guids = inventory.all_affix_guids()
    # User deselects e2
    checked_after_deselect = all_guids - {"e2"}
    sel = collapse_pos_grouped(checked_after_deselect, inventory)
    assert sel.affix_picks == frozenset(["e1", "e3"])
    assert "e2" not in sel.affix_picks


def test_preselect_all_junk_drawer_included():
    """Affixes in the junk drawer (no POS, no analysis) are also preselected."""
    from _fakes_affix import make_no_pos_entry, make_no_analysis_entry
    pos_v = make_pos("pv", "v")
    e_normal = make_infl_entry("en", "-s", ["g"], pos_v)
    e_nopos = make_no_pos_entry("ep", "-x")
    e_noanalysis = make_no_analysis_entry("ea", "-y")
    source = make_source([e_normal, e_nopos, e_noanalysis], [pos_v])
    inventory = build_pos_grouped_inventory(source)
    all_guids = inventory.all_affix_guids()
    # All three should appear
    assert "en" in all_guids
    assert "ep" in all_guids
    assert "ea" in all_guids
    # Collapse with all checked
    sel = collapse_pos_grouped(all_guids, inventory)
    assert "en" in sel.affix_picks
