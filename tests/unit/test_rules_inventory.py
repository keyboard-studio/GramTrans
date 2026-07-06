"""T020 / T027 -- build_rules_inventory: grouping, counts, preselect-all,
target_status (NEW/IN TARGET/blank), has_any, empty category.

Tests:
- Two categories present (adhoc + compound), counts correct.
- All rows preselected (checked=True, FR-009).
- target_status NEW when rule absent from target (fresh target).
- target_status IN TARGET when GUID matches (source=target equivalent).
- target_status blank ("") when target is None.
- Empty adhoc category renders without error; empty compound too.
- Grouping node structure: parent_group_guid set on children, None on group node.
- has_any True when rules exist; False when both categories empty.
- GOLD-reserved rules are excluded from the inventory.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.selection import build_rules_inventory


# ============================================================================
# Fakes
# ============================================================================

class FakeRule:
    """Minimal fake for a rule LCM object."""

    def __init__(self, guid: str, class_name: str, label: str = "",
                 is_gold: bool = False, members=None):
        self.guid = guid.lower()
        self.class_name = class_name
        self.ClassName = class_name
        self._is_gold = is_gold
        self.IsProtected = is_gold
        self.CatalogSourceId = "GOLD" if is_gold else None
        self._label = label
        self.MembersOC = members  # list or None
        self.concrete = self

    class _NameProxy:
        def __init__(self, text):
            self.BestAnalysisAlternative = type("T", (), {"Text": text})()

    @property
    def Name(self):
        return self._NameProxy(self._label) if self._label else None


class FakeMorphData:
    def __init__(self, adhoc=(), compound=()):
        self.AdhocCoProhibitionsOC = list(adhoc)
        self.CompoundRulesOS = list(compound)


class FakeLangProject:
    def __init__(self, adhoc=(), compound=()):
        self.MorphologicalDataOA = FakeMorphData(adhoc, compound)


class FakeCache:
    def __init__(self, adhoc=(), compound=()):
        self.LangProject = FakeLangProject(adhoc, compound)


class FakeProject:
    def __init__(self, adhoc=(), compound=()):
        self.Cache = FakeCache(adhoc, compound)


# ============================================================================
# T020 -- Two categories, counts, preselect-all, empty, has_any
# ============================================================================

def test_two_categories_with_correct_counts():
    adhoc_rules = [
        FakeRule("aa01", "MoAlloAdhocProhib", "allo rule 1"),
        FakeRule("aa02", "MoMorphAdhocProhib", "morph rule 2"),
    ]
    compound_rules = [
        FakeRule("cc01", "MoEndoCompound", "endo compound"),
    ]
    src = FakeProject(adhoc=adhoc_rules, compound=compound_rules)
    inv = build_rules_inventory(src)
    assert inv.adhoc.count == 2
    assert inv.compound.count == 1
    assert inv.adhoc.category_label == "Ad Hoc Rules"
    assert inv.compound.category_label == "Compound Rules"


def test_all_rows_preselected_by_default():
    adhoc_rules = [FakeRule("a1", "MoAlloAdhocProhib")]
    compound_rules = [FakeRule("c1", "MoEndoCompound")]
    src = FakeProject(adhoc=adhoc_rules, compound=compound_rules)
    inv = build_rules_inventory(src)
    for row in inv.adhoc.rows:
        assert row.checked is True, f"Row {row.guid} should be checked"
    for row in inv.compound.rows:
        assert row.checked is True, f"Row {row.guid} should be checked"


def test_empty_adhoc_category_renders_without_error():
    src = FakeProject(adhoc=[], compound=[FakeRule("c1", "MoEndoCompound")])
    inv = build_rules_inventory(src)
    assert inv.adhoc.count == 0
    assert inv.adhoc.rows == ()
    assert inv.compound.count == 1


def test_empty_compound_category_renders_without_error():
    src = FakeProject(adhoc=[FakeRule("a1", "MoAlloAdhocProhib")], compound=[])
    inv = build_rules_inventory(src)
    assert inv.compound.count == 0
    assert inv.compound.rows == ()
    assert inv.adhoc.count == 1


def test_has_any_true_when_rules_exist():
    src = FakeProject(adhoc=[FakeRule("a1", "MoAlloAdhocProhib")])
    inv = build_rules_inventory(src)
    assert inv.has_any is True


def test_has_any_false_when_both_categories_empty():
    src = FakeProject(adhoc=[], compound=[])
    inv = build_rules_inventory(src)
    assert inv.has_any is False


def test_gold_rules_excluded():
    gold = FakeRule("gold01", "MoEndoCompound", is_gold=True)
    normal = FakeRule("norm01", "MoEndoCompound")
    src = FakeProject(compound=[gold, normal])
    inv = build_rules_inventory(src)
    guids = {r.guid for r in inv.compound.rows}
    assert "gold01" not in guids
    assert "norm01" in guids


def test_grouping_node_children_have_parent_guid():
    """A group node's children get parent_group_guid set to the group's GUID."""
    child1 = FakeRule("child01", "MoAlloAdhocProhib", "child rule 1")
    child1.MembersOC = None
    group = FakeRule("group01", "MoAdhocProhibGr", "group node",
                     members=[child1])
    src = FakeProject(adhoc=[group])
    inv = build_rules_inventory(src)
    guids_pg = {r.guid: r.parent_group_guid for r in inv.adhoc.rows}
    # Group node itself has no parent
    assert guids_pg.get("group01") is None
    # Child has parent_group_guid set to group's guid
    assert guids_pg.get("child01") == "group01"


# ============================================================================
# T027 -- target_status: IN TARGET / NEW / blank(None target)
# ============================================================================

def test_target_status_blank_when_no_target():
    src = FakeProject(
        adhoc=[FakeRule("a1", "MoAlloAdhocProhib")],
        compound=[FakeRule("c1", "MoEndoCompound")],
    )
    inv = build_rules_inventory(src, target=None)
    for row in list(inv.adhoc.rows) + list(inv.compound.rows):
        assert row.target_status == "", (
            f"Expected blank target_status when no target, got {row.target_status!r}"
        )


def test_target_status_in_target_when_guid_matches():
    """Source=target equivalent: all rows should show IN TARGET."""
    rule = FakeRule("r01", "MoEndoCompound", "test rule")
    src = FakeProject(compound=[rule])
    # Target has the same GUID
    tgt_rule = FakeRule("r01", "MoEndoCompound", "test rule")
    tgt = FakeProject(compound=[tgt_rule])
    inv = build_rules_inventory(src, target=tgt)
    assert inv.compound.rows[0].target_status == "IN TARGET"


def test_target_status_new_when_guid_absent_from_target():
    """Fresh target (different GUIDs): all rows should show NEW."""
    rule = FakeRule("fresh01", "MoEndoCompound", "new rule")
    src = FakeProject(compound=[rule])
    tgt = FakeProject(compound=[])  # empty target
    inv = build_rules_inventory(src, target=tgt)
    assert inv.compound.rows[0].target_status == "NEW"


def test_target_status_mixed_in_same_inventory():
    """Some rows IN TARGET, some NEW in the same inventory."""
    r_existing = FakeRule("exist01", "MoEndoCompound", "existing rule")
    r_new = FakeRule("new01", "MoExoCompound", "new rule")
    src = FakeProject(compound=[r_existing, r_new])
    tgt_rule = FakeRule("exist01", "MoEndoCompound", "existing rule")
    tgt = FakeProject(compound=[tgt_rule])
    inv = build_rules_inventory(src, target=tgt)
    statuses = {r.guid: r.target_status for r in inv.compound.rows}
    assert statuses["exist01"] == "IN TARGET"
    assert statuses["new01"] == "NEW"
