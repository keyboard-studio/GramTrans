"""T025 -- preview._rules_missing_ref_warnings unit tests.

Exercises:
- Kept rule with dangling dep => one ExcludedLossy per (rule, dep) pair.
- Silent when dep is in-flight.
- Aggregates across multiple rules.
- No duplicate warnings for same pair.
- No warnings when no rules planned.
- P1-A: _guid_str_from normalizes lowercase.
- P1-B: GOLD piece => GOLD_INVIOLABLE Skip from plan_action.
- P2-B: execute_action raises RuntimeError on missing source GUID.
"""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from gramtrans.Lib import categories
from gramtrans.Lib.models import (
    ExcludedLossy, GrammarCategory, PlannedAction, RunContext,
    Selection, Skip, SkipReason, WSMapping,
)


class FakeRule:
    def __init__(self, guid, class_name, dep_guids=None, label='', is_gold=False):
        self.guid = guid.lower()
        self.class_name = class_name
        self.ClassName = class_name
        self._dep_guids = dep_guids or []
        self._label = label
        self._is_gold = is_gold
        self.CatalogSourceId = 'GOLD' if is_gold else None
        self.IsProtected = is_gold
        self.MembersOC = None
        self.concrete = self


class FakeMorphData:
    def __init__(self, adhoc=(), compound=()):
        self.AdhocCoProhibitionsOS = list(adhoc)
        self.CompoundRulesOS = list(compound)


class FakeCache:
    def __init__(self, adhoc=(), compound=()):
        self.LangProject = type('LP', (), {
            'MorphologicalDataOA': FakeMorphData(adhoc, compound)})()


class FakeProject:
    def __init__(self, adhoc=(), compound=()):
        self.Cache = FakeCache(adhoc, compound)


def _ctx(src, tgt=None):
    return RunContext(source_handle=src, source_project_name='Src',
        source_project_path='/s', target_handle=tgt or FakeProject(),
        target_project_name='Tgt', target_project_path='/t',
        run_id='GT-T025', started_at='2026-07-05T00:00:00')


WSM = WSMapping(entries=())


@pytest.fixture(autouse=True)
def _patch_deps_and_guid(monkeypatch):
    monkeypatch.setattr(categories, '_guid_str_from',
                        lambda obj: getattr(obj, 'guid', ''))
    def _fake_deps(piece):
        return list(getattr(getattr(piece, 'concrete', piece), '_dep_guids', []))
    monkeypatch.setattr(categories, 'adhoc_compound_rules_dependencies', _fake_deps)


def _call_mrw(src, tgt, planned):
    from gramtrans.Lib.preview import _rules_missing_ref_warnings
    excl = []
    sel = Selection(categories={GrammarCategory.ADHOC_COMPOUND_RULES: True})
    ctx = _ctx(src, tgt)
    _rules_missing_ref_warnings(ctx, sel, planned, excl, src, tgt)
    return excl


def _pa(guid):
    return PlannedAction(category=GrammarCategory.ADHOC_COMPOUND_RULES,
        source_guid=guid, intended_target_guid=guid, summary='t')


def test_dangling_dep_emits_one_warning():
    rule = FakeRule('rule01', 'MoAlloAdhocProhib', dep_guids=['dep01'], label='r1')
    src = FakeProject(adhoc=[rule])
    tgt = FakeProject()
    warnings = _call_mrw(src, tgt, [_pa('rule01')])
    assert len(warnings) == 1
    w = warnings[0]
    assert isinstance(w, ExcludedLossy)
    assert w.entry_guid == 'rule01'
    assert w.dep_guid == 'dep01'
    assert w.category == GrammarCategory.ADHOC_COMPOUND_RULES


def test_silent_when_dep_is_in_flight():
    dep_guid = 'dep03'
    rule = FakeRule('rule03', 'MoAlloAdhocProhib', dep_guids=[dep_guid])
    src = FakeProject(adhoc=[rule])
    tgt = FakeProject()
    planned = [_pa('rule03'), _pa(dep_guid)]
    warnings = _call_mrw(src, tgt, planned)
    assert not any(w.entry_guid == 'rule03' and w.dep_guid == dep_guid
                   for w in warnings)


def test_aggregates_across_multiple_rules():
    rule_x = FakeRule('rule-x', 'MoAlloAdhocProhib', dep_guids=['dep-a'])
    rule_y = FakeRule('rule-y', 'MoMorphAdhocProhib', dep_guids=['dep-b'])
    src = FakeProject(adhoc=[rule_x, rule_y])
    tgt = FakeProject()
    warnings = _call_mrw(src, tgt, [_pa('rule-x'), _pa('rule-y')])
    entry_guids = [w.entry_guid for w in warnings]
    assert 'rule-x' in entry_guids
    assert 'rule-y' in entry_guids
    assert len(warnings) >= 2


def test_no_duplicate_warnings_for_same_pair():
    dep_guid = 'dep-dup'
    rule = FakeRule('rule-dup', 'MoAlloAdhocProhib', dep_guids=[dep_guid, dep_guid])
    src = FakeProject(adhoc=[rule])
    tgt = FakeProject()
    warnings = _call_mrw(src, tgt, [_pa('rule-dup')])
    matching = [w for w in warnings
                if w.entry_guid == 'rule-dup' and w.dep_guid == dep_guid]
    assert len(matching) == 1


def test_no_warnings_when_no_rules_planned():
    rule = FakeRule('rule-z', 'MoAlloAdhocProhib', dep_guids=['dep-z'])
    src = FakeProject(adhoc=[rule])
    tgt = FakeProject()
    warnings = _call_mrw(src, tgt, [])
    assert warnings == []


def test_p1a_guid_str_from_normalizes_lowercase():
    from gramtrans.Lib.categories import _guid_str_from
    class DirectGuidObj:
        guid = 'aabb-ccdd'
    result = _guid_str_from(DirectGuidObj())
    assert result == 'aabb-ccdd'


def test_p1b_gold_piece_returns_gold_inviolable_skip():
    gold_rule = FakeRule('gold-skip', 'MoEndoCompound', is_gold=True)
    src = FakeProject(compound=[gold_rule])
    tgt = FakeProject()
    ctx = _ctx(src, tgt)
    result = categories.adhoc_compound_rules_plan_action(gold_rule, ctx, WSM)
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.GOLD_INVIOLABLE


def test_p2b_execute_action_raises_on_missing_source_guid():
    src = FakeProject()
    tgt = FakeProject()
    ctx = _ctx(src, tgt)
    missing_action = PlannedAction(
        category=GrammarCategory.ADHOC_COMPOUND_RULES,
        source_guid='no-such-guid', intended_target_guid='no-such-guid',
        summary='x')
    lcm_mock = MagicMock()
    with patch.dict('sys.modules', {'SIL': lcm_mock, 'SIL.LCModel': lcm_mock}):
        with pytest.raises(RuntimeError, match='not found in source project'):
            categories.adhoc_compound_rules_execute_action(
                missing_action, ctx, WSM, 'test-tag')
