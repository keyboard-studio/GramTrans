"""T021 -- adhoc_compound_rules_enumerate_source: leaf_item_picks filter,
GUID normalization, grouping recursion, P1-C group-nodes-last ordering.

Tests:
- Absent key => all rules returned.
- Subset present => only matching-GUID rules returned.
- Empty frozenset => no rules returned.
- GUID normalized both sides via _guid_str_from.
- Grouping node children recurse.
- GOLD rules excluded regardless of picks.
- P1-C: group nodes sorted LAST so re-parenting is deterministic.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib import categories
from gramtrans.Lib.models import GrammarCategory, RunContext, Selection


class FakeRule:
    def __init__(self, guid, class_name, is_gold=False, members=None):
        self.guid = guid.lower()
        self.class_name = class_name
        self.ClassName = class_name
        self._is_gold = is_gold
        self.CatalogSourceId = "GOLD" if is_gold else None
        self.MembersOC = members
        self.concrete = self

    @property
    def IsProtected(self):
        return self._is_gold


class FakeMorphData:
    def __init__(self, adhoc=(), compound=()):
        self.AdhocCoProhibitionsOC = list(adhoc)
        self.CompoundRulesOS = list(compound)


class FakeCache:
    def __init__(self, adhoc=(), compound=()):
        self.LangProject = type("LP", (), {
            "MorphologicalDataOA": FakeMorphData(adhoc, compound)
        })()


class FakeProject:
    def __init__(self, adhoc=(), compound=()):
        self.Cache = FakeCache(adhoc, compound)


def _ctx(src, tgt=None):
    return RunContext(
        source_handle=src, source_project_name="Src", source_project_path="/s",
        target_handle=tgt or FakeProject(), target_project_name="Tgt",
        target_project_path="/t", run_id="GT-20260705-T021",
        started_at="2026-07-05T00:00:00",
    )


@pytest.fixture(autouse=True)
def _patch_guid(monkeypatch):
    monkeypatch.setattr(categories, "_guid_str_from", lambda obj: getattr(obj, "guid", ""))


ALL_FIVE = ["MoAlloAdhocProhib", "MoMorphAdhocProhib", "MoAdhocProhibGr",
            "MoEndoCompound", "MoExoCompound"]


def _make_five():
    return [FakeRule(f"g-{cn[:4].lower()}", cn) for cn in ALL_FIVE]


def test_absent_key_returns_all():
    rules = _make_five()
    src = FakeProject(adhoc=rules[:3], compound=rules[3:])
    sel = Selection(categories={GrammarCategory.ADHOC_COMPOUND_RULES: True})
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src), sel)
    assert {r.guid for r in result} == {r.guid for r in rules}


def test_subset_present_returns_only_subset():
    rules = _make_five()
    src = FakeProject(adhoc=rules[:3], compound=rules[3:])
    kept = frozenset({rules[0].guid, rules[4].guid})
    sel = Selection(
        categories={GrammarCategory.ADHOC_COMPOUND_RULES: True},
        leaf_item_picks={GrammarCategory.ADHOC_COMPOUND_RULES: kept},
    )
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src), sel)
    assert {r.guid for r in result} == kept


def test_empty_frozenset_returns_none():
    rules = _make_five()
    src = FakeProject(adhoc=rules[:3], compound=rules[3:])
    sel = Selection(
        categories={GrammarCategory.ADHOC_COMPOUND_RULES: True},
        leaf_item_picks={GrammarCategory.ADHOC_COMPOUND_RULES: frozenset()},
    )
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src), sel)
    assert list(result) == []


def test_guid_normalization_uppercase_pick_misses():
    """Un-normalized (uppercase) pick misses the rule -- invariant proof."""
    rule = FakeRule("abc123", "MoEndoCompound")
    src = FakeProject(compound=[rule])
    sel = Selection(
        categories={GrammarCategory.ADHOC_COMPOUND_RULES: True},
        leaf_item_picks={GrammarCategory.ADHOC_COMPOUND_RULES: frozenset({"ABC123"})},
    )
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src), sel)
    assert list(result) == []


def test_guid_normalization_lowercase_pick_matches():
    rule = FakeRule("abc123", "MoEndoCompound")
    src = FakeProject(compound=[rule])
    sel = Selection(
        categories={GrammarCategory.ADHOC_COMPOUND_RULES: True},
        leaf_item_picks={GrammarCategory.ADHOC_COMPOUND_RULES: frozenset({"abc123"})},
    )
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src), sel)
    assert {r.guid for r in result} == {"abc123"}


def test_grouping_recursion_yields_group_and_child():
    child = FakeRule("child01", "MoAlloAdhocProhib")
    group = FakeRule("group01", "MoAdhocProhibGr", members=[child])
    src = FakeProject(adhoc=[group])
    sel = Selection(categories={GrammarCategory.ADHOC_COMPOUND_RULES: True})
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src), sel)
    guids = {r.guid for r in result}
    assert "group01" in guids
    assert "child01" in guids


def test_grouping_children_filtered_by_subset_pick():
    child = FakeRule("child01", "MoAlloAdhocProhib")
    group = FakeRule("group01", "MoAdhocProhibGr", members=[child])
    src = FakeProject(adhoc=[group])
    sel = Selection(
        categories={GrammarCategory.ADHOC_COMPOUND_RULES: True},
        leaf_item_picks={GrammarCategory.ADHOC_COMPOUND_RULES: frozenset({"child01"})},
    )
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src), sel)
    guids = {r.guid for r in result}
    assert "child01" in guids


def test_no_gold_exclusion_all_picks_enumerated():
    """v7.0.0 GOLD unlock: enumeration applies NO GOLD-based filter, so every
    picked rule is enumerated. (Rules are not catalog-backed and never carry a
    real GOLD flag, so an is_gold fake is unrealistic; this confirms the former
    defensive filter is gone.)"""
    other = FakeRule("gold01", "MoEndoCompound", is_gold=True)
    normal = FakeRule("norm01", "MoEndoCompound")
    src = FakeProject(compound=[other, normal])
    sel = Selection(
        categories={GrammarCategory.ADHOC_COMPOUND_RULES: True},
        leaf_item_picks={GrammarCategory.ADHOC_COMPOUND_RULES: frozenset({"gold01", "norm01"})},
    )
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src), sel)
    guids = {r.guid for r in result}
    assert "gold01" in guids
    assert "norm01" in guids


def test_group_nodes_sorted_last_in_enumerate():
    """P1-C: group nodes must appear after non-group nodes in the result."""
    child1 = FakeRule("ch-a", "MoAlloAdhocProhib")
    group = FakeRule("gr-a", "MoAdhocProhibGr", members=[child1])
    child2 = FakeRule("ch-b", "MoMorphAdhocProhib")
    # Source order: group first, then child2 at top level
    src = FakeProject(adhoc=[group, child2])
    sel = Selection(categories={GrammarCategory.ADHOC_COMPOUND_RULES: True})
    result = list(categories.adhoc_compound_rules_enumerate_source(_ctx(src), sel))
    guids = [r.guid for r in result]
    group_idx = guids.index("gr-a")
    assert "ch-b" in guids
    assert guids.index("ch-b") < group_idx, (
        "Non-group 'ch-b' must appear before group 'gr-a' in enumerate result (P1-C)"
    )
