"""T012 -- adhoc_compound_rules engine: plan dispatch (fake handles).

Tests:
- _rule_subclass_info returns correct (class_name, factory, ref_spec) for all
  five subclasses.
- Unknown ClassName raises RuntimeError loudly (FR-006/SC-008).
- adhoc_compound_rules_plan_action: GUID-first Skip/Add per subclass.
- Idempotent re-plan: a rule already present by GUID -> Skip.
- adhoc_compound_rules_enumerate_source: absent key => all; subset key => subset;
  empty key => none; excludes GOLD-reserved items.
- adhoc_compound_rules_required_writing_systems returns ().

All five subclasses covered: MoAlloAdhocProhib, MoMorphAdhocProhib,
MoAdhocProhibGr, MoEndoCompound, MoExoCompound.

Live execute_action coverage (endo) is in tests/integration/test_rules_live.py;
adhoc + exo live coverage deferred (no live project with those objects confirmed
in probe-results.md [CONFIRMED LIVE 2026-07-05]).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from gramtrans.Lib import categories
from gramtrans.Lib.models import (
    GrammarCategory,
    PlannedAction,
    RunContext,
    Selection,
    Skip,
    SkipReason,
    WSMapping,
)


# =============================================================================
# Fake handles
# =============================================================================

class FakeRule:
    """Minimal fake for a rule object with a GUID and ClassName."""

    def __init__(self, guid: str, class_name: str, is_gold: bool = False):
        self.guid = guid.lower()
        self.class_name = class_name  # read by _rule_subclass_info in test mode
        self.ClassName = class_name   # alternate attr name
        self._is_gold = is_gold
        # Expose .concrete == self so unwrap is a no-op
        self.concrete = self

    # Duck-type _is_gold_source check (categories._is_gold_source checks CatalogSourceId)
    @property
    def CatalogSourceId(self):
        return "GOLD" if self._is_gold else None


class FakeRulesCollection:
    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)


class FakeMorphData:
    def __init__(self, adhoc=(), compound=()):
        self.AdhocCoProhibitionsOC = FakeRulesCollection(adhoc)
        self.CompoundRulesOS = FakeRulesCollection(compound)


class FakeCache:
    def __init__(self, adhoc=(), compound=()):
        self.LangProject = type("LP", (), {
            "MorphologicalDataOA": FakeMorphData(adhoc, compound),
        })()


class FakeSource:
    def __init__(self, adhoc=(), compound=()):
        self.Cache = FakeCache(adhoc, compound)
        self._adhoc = list(adhoc)
        self._compound = list(compound)


class FakeTarget:
    def __init__(self, adhoc=(), compound=()):
        self.Cache = FakeCache(adhoc, compound)


def _ctx(src, tgt) -> RunContext:
    return RunContext(
        source_handle=src, source_project_name="Src", source_project_path="/s",
        target_handle=tgt, target_project_name="Tgt", target_project_path="/t",
        run_id="GT-20260705-000000", started_at="2026-07-05T00:00:00",
    )


WSM = WSMapping(entries=())
SEL = Selection(categories={})


# Patch _guid_str_from to use the fake's .guid attribute directly (no LCM).
@pytest.fixture(autouse=True)
def _patch_guid(monkeypatch):
    monkeypatch.setattr(categories, "_guid_str_from", lambda obj: getattr(obj, "guid", ""))


# =============================================================================
# T003 -- _rule_subclass_info dispatch
# =============================================================================

ALL_FIVE_SUBCLASSES = [
    "MoAlloAdhocProhib",
    "MoMorphAdhocProhib",
    "MoAdhocProhibGr",
    "MoEndoCompound",
    "MoExoCompound",
]

@pytest.mark.parametrize("class_name", ALL_FIVE_SUBCLASSES)
def test_rule_subclass_info_returns_tuple_for_known(class_name):
    """_rule_subclass_info returns a 3-tuple for each of the five subclasses."""
    rule = FakeRule("aaaa-1111", class_name)
    # Patch ICmObject import so the function falls back to fake .class_name attr
    with patch.dict("sys.modules", {"SIL": None, "SIL.LCModel": None}):
        # The function catches ImportError and falls back to getattr(obj, 'class_name')
        info = categories._rule_subclass_info(rule)
    assert isinstance(info, tuple)
    assert len(info) == 3
    cn, factory, ref_spec = info
    assert cn == class_name
    assert isinstance(ref_spec, dict)


def test_rule_subclass_info_raises_on_unknown():
    """Unknown ClassName raises RuntimeError loudly (FR-006/SC-008)."""
    rule = FakeRule("dead-beef", "UnknownRuleClass")
    with patch.dict("sys.modules", {"SIL": None, "SIL.LCModel": None}):
        with pytest.raises(RuntimeError, match="unrecognised ClassName"):
            categories._rule_subclass_info(rule)


def test_rule_subclass_info_unwraps_concrete():
    """Wrapper objects with .concrete are unwrapped before dispatch."""
    inner = FakeRule("bbbb-2222", "MoEndoCompound")
    wrapper = type("Wrapper", (), {"concrete": inner})()
    with patch.dict("sys.modules", {"SIL": None, "SIL.LCModel": None}):
        cn, _factory, _ref_spec = categories._rule_subclass_info(wrapper)
    assert cn == "MoEndoCompound"


# =============================================================================
# T003 ref_spec shape
# =============================================================================

def test_allo_adhoc_ref_spec_has_expected_fields():
    rule = FakeRule("a1", "MoAlloAdhocProhib")
    with patch.dict("sys.modules", {"SIL": None, "SIL.LCModel": None}):
        _cn, _fac, ref_spec = categories._rule_subclass_info(rule)
    assert "FirstAllomorphRA" in ref_spec
    assert "RestOfAllosRS" in ref_spec
    assert "AllomorphsRS" in ref_spec


def test_morph_adhoc_ref_spec_has_expected_fields():
    rule = FakeRule("a2", "MoMorphAdhocProhib")
    with patch.dict("sys.modules", {"SIL": None, "SIL.LCModel": None}):
        _cn, _fac, ref_spec = categories._rule_subclass_info(rule)
    assert "FirstMorphemeRA" in ref_spec
    assert "RestOfMorphsRS" in ref_spec
    assert "MorphemesRS" in ref_spec


@pytest.mark.parametrize("class_name", ["MoAdhocProhibGr", "MoEndoCompound", "MoExoCompound"])
def test_non_ref_subclasses_have_empty_ref_spec(class_name):
    """Group and compound subclasses use dedicated wiring, not ref_spec."""
    rule = FakeRule("a3", class_name)
    with patch.dict("sys.modules", {"SIL": None, "SIL.LCModel": None}):
        _cn, _fac, ref_spec = categories._rule_subclass_info(rule)
    assert ref_spec == {}


# =============================================================================
# T004/T005 -- _rules_enumerate_all + adhoc_compound_rules_enumerate_source
# =============================================================================

def _make_five_rules():
    return [FakeRule(f"guid-{cn[:4].lower()}", cn) for cn in ALL_FIVE_SUBCLASSES]


def test_enumerate_all_yields_from_both_collections():
    rules = _make_five_rules()
    adhoc = rules[:3]
    compound = rules[3:]
    src = FakeSource(adhoc=adhoc, compound=compound)
    result = list(categories._rules_enumerate_all(src))
    guids = {r.guid for r in result}
    assert guids == {r.guid for r in rules}


def test_enumerate_all_recurses_into_members_oc():
    """IMoAdhocProhibGr children in MembersOC are yielded."""
    child = FakeRule("child-guid", "MoAlloAdhocProhib")
    parent = FakeRule("group-guid", "MoAdhocProhibGr")
    parent.MembersOC = [child]
    src = FakeSource(adhoc=[parent])
    result = list(categories._rules_enumerate_all(src))
    guids = {r.guid for r in result}
    assert "group-guid" in guids
    assert "child-guid" in guids


def test_enumerate_source_absent_key_returns_all():
    rules = _make_five_rules()
    src = FakeSource(adhoc=rules[:3], compound=rules[3:])
    tgt = FakeTarget()
    sel = Selection(categories={GrammarCategory.ADHOC_COMPOUND_RULES: True})
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src, tgt), sel)
    assert len(result) == 5


def test_enumerate_source_subset_key_filters():
    rules = _make_five_rules()
    src = FakeSource(adhoc=rules[:3], compound=rules[3:])
    tgt = FakeTarget()
    kept_guids = frozenset({rules[0].guid, rules[4].guid})
    sel = Selection(
        categories={GrammarCategory.ADHOC_COMPOUND_RULES: True},
        leaf_item_picks={GrammarCategory.ADHOC_COMPOUND_RULES: kept_guids},
    )
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src, tgt), sel)
    assert {r.guid for r in result} == kept_guids


def test_enumerate_source_empty_frozenset_returns_none():
    rules = _make_five_rules()
    src = FakeSource(adhoc=rules[:3], compound=rules[3:])
    tgt = FakeTarget()
    sel = Selection(
        categories={GrammarCategory.ADHOC_COMPOUND_RULES: True},
        leaf_item_picks={GrammarCategory.ADHOC_COMPOUND_RULES: frozenset()},
    )
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src, tgt), sel)
    assert result == []


def test_enumerate_source_no_gold_filtering():
    """v7.0.0 GOLD unlock: enumeration applies NO GOLD-based filter; every rule
    is enumerated. (Rules are not catalog-backed and never carry a real GOLD
    flag, so an is_gold fake is unrealistic; this confirms the defensive filter
    is gone.)"""
    other = FakeRule("gold-guid", "MoEndoCompound", is_gold=True)
    normal = FakeRule("norm-guid", "MoEndoCompound", is_gold=False)
    src = FakeSource(compound=[other, normal])
    tgt = FakeTarget()
    sel = Selection(categories={GrammarCategory.ADHOC_COMPOUND_RULES: True})
    result = categories.adhoc_compound_rules_enumerate_source(_ctx(src, tgt), sel)
    guids = {r.guid for r in result}
    assert "gold-guid" in guids
    assert "norm-guid" in guids


# =============================================================================
# T006 -- required_writing_systems returns ()
# =============================================================================

@pytest.mark.parametrize("class_name", ALL_FIVE_SUBCLASSES)
def test_required_writing_systems_returns_empty(class_name):
    rule = FakeRule("ws-guid", class_name)
    result = categories.adhoc_compound_rules_required_writing_systems(rule)
    assert result == ()


# =============================================================================
# T007 -- plan_action GUID-first skip/add
# =============================================================================

@pytest.mark.parametrize("class_name", ALL_FIVE_SUBCLASSES)
def test_plan_action_returns_planned_action_for_new_rule(class_name):
    rule = FakeRule(f"new-{class_name[:4].lower()}", class_name)
    src = FakeSource(compound=[rule])
    tgt = FakeTarget()  # empty target
    result = categories.adhoc_compound_rules_plan_action(rule, _ctx(src, tgt), WSM)
    assert isinstance(result, PlannedAction)
    assert result.category == GrammarCategory.ADHOC_COMPOUND_RULES
    assert result.source_guid == rule.guid


@pytest.mark.parametrize("class_name", ALL_FIVE_SUBCLASSES)
def test_plan_action_skips_existing_guid(class_name):
    """GUID-first: rule already in target => Skip(ALREADY_PRESENT_BY_GUID)."""
    rule = FakeRule(f"dup-{class_name[:4].lower()}", class_name)
    src = FakeSource(compound=[rule])
    # Place same GUID in target
    tgt_rule = FakeRule(rule.guid, class_name)
    tgt = FakeTarget(compound=[tgt_rule])
    result = categories.adhoc_compound_rules_plan_action(rule, _ctx(src, tgt), WSM)
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID


def test_plan_action_idempotent_replan():
    """Re-planning after GUID is present still yields Skip (SC-001/002)."""
    rule = FakeRule("idem-guid", "MoEndoCompound")
    src = FakeSource(compound=[rule])
    tgt_rule = FakeRule(rule.guid, "MoEndoCompound")
    tgt = FakeTarget(compound=[tgt_rule])
    ctx = _ctx(src, tgt)
    r1 = categories.adhoc_compound_rules_plan_action(rule, ctx, WSM)
    r2 = categories.adhoc_compound_rules_plan_action(rule, ctx, WSM)
    assert isinstance(r1, Skip)
    assert isinstance(r2, Skip)
    assert r1.reason == r2.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# =============================================================================
# SC-008 -- unknown subclass raises loudly via _rule_subclass_info
# =============================================================================

def test_unknown_subclass_raises_loudly():
    """_rule_subclass_info with unknown ClassName raises RuntimeError."""
    rule = FakeRule("xxxx-yyyy", "IMoUnknownFoo")
    with patch.dict("sys.modules", {"SIL": None, "SIL.LCModel": None}):
        with pytest.raises(RuntimeError, match="unrecognised ClassName"):
            categories._rule_subclass_info(rule)


# =============================================================================
# Subclass-cast regression (base-interface hides subclass slots)
# =============================================================================
# Live-confirmed 2026-07-05 (Esperanto): a base-typed IMoCompoundRule read via
# pythonnet hides LeftMsaOA/RightMsaOA/etc. (0/5 visible); casting to
# IMoEndoCompound exposes them (5/5). _cast_rule_concrete performs that cast at
# the enumerate choke point. In the fake-handle env SIL.LCModel is absent, so the
# helper must pass objects through UNCHANGED (fakes expose attributes directly).

def test_cast_rule_concrete_passthrough_without_lcm():
    """_cast_rule_concrete returns fakes unchanged when SIL.LCModel is absent."""
    rule = FakeRule("aaaa-bbbb", "MoEndoCompound")
    with patch.dict("sys.modules", {"SIL": None, "SIL.LCModel": None}):
        assert categories._cast_rule_concrete(rule) is rule


def test_enumerate_all_applies_cast(monkeypatch):
    """_rules_enumerate_all routes every yielded object through _cast_rule_concrete
    (guards the base-interface-hiding regression)."""
    seen = []

    def _spy(obj):
        seen.append(obj)
        return obj

    monkeypatch.setattr(categories, "_cast_rule_concrete", _spy)
    endo = FakeRule("11", "MoEndoCompound")
    allo = FakeRule("22", "MoAlloAdhocProhib")
    src = FakeSource(adhoc=[allo], compound=[endo])
    out = list(categories._rules_enumerate_all(src))
    # every enumerated object passed through the cast helper
    assert endo in seen and allo in seen
    assert endo in out and allo in out
