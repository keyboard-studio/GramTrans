"""Phase 3a -- phonology block + strata Python-surface tests.

Tests the enumerate_source / dependencies / plan_action callbacks for
the six Phase 3a categories.  execute_action requires live LCM and is
exercised at live MCP time (integration tests in
tests/integration/test_phase3a_phonology_e2e.py).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gramtrans.Lib import categories
from gramtrans.Lib.models import (
    GrammarCategory,
    PlannedAction,
    RunContext,
    Selection,
    Skip,
    SkipReason,
    WSKind,
    WSMapping,
)


# ============================================================================
# Fakes
# ============================================================================

class _Item:
    def __init__(self, guid):
        self.guid = guid
        self.Guid = guid  # mimics ICmObject.Guid for _guid_str_from

    @property
    def concrete(self):
        return self


class _Ops:
    def __init__(self, items):
        self._items = list(items)

    def GetAll(self):
        return list(self._items)


def _project(**ops):
    p = type("P", (), {})()
    for attr, items in ops.items():
        setattr(p, attr, _Ops(items))
    return p


def _ctx(src, tgt) -> RunContext:
    return RunContext(
        source_handle=src, source_project_name="Src", source_project_path="/s",
        target_handle=tgt, target_project_name="Tgt", target_project_path="/t",
        run_id="GT-20260620-010000", started_at="2026-06-20T01:00:00",
    )


WSM = WSMapping(entries=())
SEL = Selection(categories={})


# Patch _guid_str_from to use the test fake's `guid` attribute directly.
@pytest.fixture(autouse=True)
def _patch_guid_helpers(monkeypatch):
    monkeypatch.setattr(categories, "_guid_str_from", lambda obj: obj.guid)


# ============================================================================
# Phon Features
# ============================================================================

def test_phon_features_enumerate_returns_source_features():
    src = _project(PhonFeatures=[_Item("a-1"), _Item("a-2")])
    tgt = _project(PhonFeatures=[])
    assert len(categories.phonological_features_enumerate_source(_ctx(src, tgt), SEL)) == 2


def test_phon_features_enumerate_empty_when_attr_missing():
    src = _project()  # no PhonFeatures attr
    tgt = _project()
    assert categories.phonological_features_enumerate_source(_ctx(src, tgt), SEL) == ()


def test_phon_features_dependencies_empty():
    assert categories.phonological_features_dependencies(_Item("a")) == ()


def test_phon_features_required_writing_systems_empty():
    assert categories.phonological_features_required_writing_systems(_Item("a")) == ()


def test_phon_features_plan_action_emits_planned_for_new_guid():
    src = _project(PhonFeatures=[_Item("f-1")])
    tgt = _project(PhonFeatures=[])
    piece = _Item("f-1")
    action = categories.phonological_features_plan_action(piece, _ctx(src, tgt), WSM)
    assert isinstance(action, PlannedAction)
    assert action.category == GrammarCategory.PHONOLOGICAL_FEATURES
    assert action.source_guid == "f-1"


def test_phon_features_plan_action_skips_when_present():
    src = _project(PhonFeatures=[_Item("f-1")])
    tgt = _project(PhonFeatures=[_Item("f-1")])
    skip = categories.phonological_features_plan_action(_Item("f-1"), _ctx(src, tgt), WSM)
    assert isinstance(skip, Skip)
    assert skip.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ============================================================================
# Phonemes
# ============================================================================

def test_phonemes_enumerate_returns_source():
    src = _project(Phonemes=[_Item("p-1"), _Item("p-2"), _Item("p-3")])
    tgt = _project(Phonemes=[])
    assert len(categories.phonemes_enumerate_source(_ctx(src, tgt), SEL)) == 3


def test_phonemes_plan_action_emits_planned_for_new_guid():
    src = _project(Phonemes=[_Item("p-1")])
    tgt = _project(Phonemes=[])
    action = categories.phonemes_plan_action(_Item("p-1"), _ctx(src, tgt), WSM)
    assert isinstance(action, PlannedAction)
    assert action.category == GrammarCategory.PHONEMES


def test_phonemes_plan_action_skips_when_present():
    src = _project(Phonemes=[_Item("p-1")])
    tgt = _project(Phonemes=[_Item("p-1")])
    skip = categories.phonemes_plan_action(_Item("p-1"), _ctx(src, tgt), WSM)
    assert isinstance(skip, Skip)
    assert skip.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ============================================================================
# Natural Classes
# ============================================================================

def test_natural_classes_enumerate_returns_source():
    src = _project(NaturalClasses=[_Item("nc-1"), _Item("nc-2")])
    tgt = _project(NaturalClasses=[])
    assert len(categories.natural_classes_enumerate_source(_ctx(src, tgt), SEL)) == 2


def test_natural_classes_dependencies_non_lcm_returns_empty():
    """Without LCM imports available, dependencies returns empty tuple
    (the function exception-guards the SIL.LCModel imports)."""
    deps = categories.natural_classes_dependencies(_Item("nc-1"))
    # In a real LCM context this would return phoneme GUIDs; here the
    # fake doesn't quack like IPhNCSegments so the function falls through.
    assert isinstance(deps, tuple)


def test_natural_classes_plan_action_skips_when_present():
    src = _project(NaturalClasses=[_Item("nc-1")])
    tgt = _project(NaturalClasses=[_Item("nc-1")])
    skip = categories.natural_classes_plan_action(_Item("nc-1"), _ctx(src, tgt), WSM)
    assert isinstance(skip, Skip)
    assert skip.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ============================================================================
# PhEnvironment
# ============================================================================

def test_ph_environment_enumerate_returns_source():
    src = _project(Environments=[_Item("e-1"), _Item("e-2")])
    tgt = _project(Environments=[])
    assert len(categories.ph_environment_enumerate_source(_ctx(src, tgt), SEL)) == 2


def test_ph_environment_dependencies_empty():
    assert categories.ph_environment_dependencies(_Item("e-1")) == ()


def test_ph_environment_plan_action_skips_when_present():
    src = _project(Environments=[_Item("e-1")])
    tgt = _project(Environments=[_Item("e-1")])
    skip = categories.ph_environment_plan_action(_Item("e-1"), _ctx(src, tgt), WSM)
    assert isinstance(skip, Skip)


# ============================================================================
# Strata
# ============================================================================

def test_strata_enumerate_returns_source():
    src = _project(Strata=[_Item("s-1"), _Item("s-2")])
    tgt = _project(Strata=[])
    assert len(categories.strata_enumerate_source(_ctx(src, tgt), SEL)) == 2


def test_strata_dependencies_empty():
    assert categories.strata_dependencies(_Item("s-1")) == ()


def test_strata_plan_action_emits_planned_for_new_guid():
    src = _project(Strata=[_Item("s-1")])
    tgt = _project(Strata=[])
    action = categories.strata_plan_action(_Item("s-1"), _ctx(src, tgt), WSM)
    assert isinstance(action, PlannedAction)
    assert action.category == GrammarCategory.STRATA


def test_strata_plan_action_skips_when_present():
    src = _project(Strata=[_Item("s-1")])
    tgt = _project(Strata=[_Item("s-1")])
    skip = categories.strata_plan_action(_Item("s-1"), _ctx(src, tgt), WSM)
    assert isinstance(skip, Skip)
    assert skip.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ============================================================================
# Phonological Rules
# ============================================================================

def test_phonological_rules_enumerate_returns_source():
    src = _project(PhonRules=[_Item("r-1"), _Item("r-2")])
    tgt = _project(PhonRules=[])
    assert len(categories.phonological_rules_enumerate_source(_ctx(src, tgt), SEL)) == 2


def test_phonological_rules_dependencies_returns_tuple():
    """Without LCM, returns empty tuple via exception guard."""
    deps = categories.phonological_rules_dependencies(_Item("r-1"))
    assert isinstance(deps, tuple)


def test_phonological_rules_plan_action_emits_planned_for_new_guid():
    src = _project(PhonRules=[_Item("r-1")])
    tgt = _project(PhonRules=[])
    action = categories.phonological_rules_plan_action(_Item("r-1"), _ctx(src, tgt), WSM)
    assert isinstance(action, PlannedAction)
    assert action.category == GrammarCategory.PHONOLOGICAL_RULES


def test_phonological_rules_plan_action_skips_when_present():
    src = _project(PhonRules=[_Item("r-1")])
    tgt = _project(PhonRules=[_Item("r-1")])
    skip = categories.phonological_rules_plan_action(_Item("r-1"), _ctx(src, tgt), WSM)
    assert isinstance(skip, Skip)
    assert skip.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ============================================================================
# Empty-source handling (US4 / FR-308)
# ============================================================================

@pytest.mark.parametrize("enumerator", [
    categories.phonological_features_enumerate_source,
    categories.phonemes_enumerate_source,
    categories.natural_classes_enumerate_source,
    categories.ph_environment_enumerate_source,
    categories.phonological_rules_enumerate_source,
    categories.strata_enumerate_source,
])
def test_enumerate_empty_source_returns_empty(enumerator):
    """FR-308: every category's enumerate_source must tolerate a source
    that has no items for that category."""
    src = _project(PhonFeatures=[], Phonemes=[], NaturalClasses=[],
                   Environments=[], PhonRules=[], Strata=[])
    tgt = _project()
    assert enumerator(_ctx(src, tgt), SEL) == []


# ============================================================================
# _create_with_guid hardening tests
# ============================================================================

def _make_target_with_factory(factory_instance):
    """Build a minimal fake `target` whose Cache.ServiceLocator.GetService()
    returns `factory_instance`."""
    sl = MagicMock()
    sl.GetService.return_value = factory_instance
    cache = MagicMock()
    cache.ServiceLocator = sl
    target = MagicMock()
    target.Cache = cache
    return target


def test_create_with_guid_raises_runtime_error_on_add_failure():
    """If Create(Guid) succeeds but Add raises, _create_with_guid must raise
    RuntimeError mentioning 'Orphan risk' and must NOT stash the sentinel."""
    sentinel = object()

    factory = MagicMock()
    factory.Create.return_value = sentinel

    bad_collection = MagicMock()
    bad_collection.Add.side_effect = ValueError("collection locked")

    # factory_iface.__name__ used for the error message
    factory_iface = MagicMock()
    factory_iface.__name__ = "FakeFactory"

    target = _make_target_with_factory(factory)

    # Intercept `from System import Guid` inside _create_with_guid by
    # injecting a fake System module into sys.modules.
    import sys
    guid_str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    fake_guid_class = MagicMock()
    fake_guid_class.Parse.return_value = MagicMock(name="parsed_guid")
    fake_system = MagicMock()
    fake_system.Guid = fake_guid_class

    original = sys.modules.get("System")
    sys.modules["System"] = fake_system
    try:
        with pytest.raises(RuntimeError) as exc_info:
            categories._create_with_guid(factory_iface, bad_collection, guid_str, target)
    finally:
        if original is None:
            del sys.modules["System"]
        else:
            sys.modules["System"] = original

    msg = str(exc_info.value)
    assert "Orphan risk" in msg, f"Expected 'Orphan risk' in: {msg}"
    # Confirm sentinel is not reachable through any tracked collection
    bad_collection.Add.assert_called_once_with(sentinel)
    # The exception must have been raised — sentinel was never stored anywhere
    # by the helper (it has no internal list/dict).  The call to Add was the
    # only mutation attempted, and it raised, so the object is an orphan in
    # LCM memory — the error message says so and the caller is responsible.


def test_create_with_guid_raises_runtime_error_when_create_guid_unsupported():
    """If factory.Create(guid) raises, _create_with_guid must raise
    RuntimeError mentioning 'does not support Create(Guid)' and must never
    call no-arg Create()."""
    factory = MagicMock()
    factory.Create.side_effect = TypeError("no Guid overload")

    factory_iface = MagicMock()
    factory_iface.__name__ = "FakeFactory"

    owner_collection = MagicMock()

    target = _make_target_with_factory(factory)

    import sys
    fake_guid_class = MagicMock()
    fake_guid_class.Parse.return_value = MagicMock(name="parsed_guid")
    fake_system = MagicMock()
    fake_system.Guid = fake_guid_class

    guid_str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    original = sys.modules.get("System")
    sys.modules["System"] = fake_system
    try:
        with pytest.raises(RuntimeError) as exc_info:
            categories._create_with_guid(factory_iface, owner_collection, guid_str, target)
    finally:
        if original is None:
            del sys.modules["System"]
        else:
            sys.modules["System"] = original

    msg = str(exc_info.value)
    assert "does not support Create(Guid)" in msg, f"Expected 'does not support Create(Guid)' in: {msg}"

    # Create was called exactly once (with the parsed guid) — no no-arg fallback.
    assert factory.Create.call_count == 1, (
        f"Create() called {factory.Create.call_count} times; expected exactly 1 "
        "(no no-arg fallback allowed)"
    )
    # Add must never have been called.
    owner_collection.Add.assert_not_called()


# ============================================================================
# natural_classes_execute_action -- SegmentsRC wiring (P1-C)
# ============================================================================

def _fake_sys_guid(monkeypatch):
    """Inject a fake System.Guid into sys.modules so _create_with_guid works."""
    import sys
    fake_guid_class = MagicMock()
    # Parse returns an object whose str is the original guid_str; good enough.
    fake_guid_class.Parse.side_effect = lambda s: s
    fake_system = MagicMock()
    fake_system.Guid = fake_guid_class
    original = sys.modules.get("System")
    sys.modules["System"] = fake_system
    return original


def _restore_sys_guid(original):
    import sys
    if original is None:
        sys.modules.pop("System", None)
    else:
        sys.modules["System"] = original


class _FakeCollection:
    """Minimal stand-in for an LCM reference-collection (SegmentsRC etc.)."""
    def __init__(self, items=()):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def Add(self, item):
        self._items.append(item)

    def __len__(self):
        return len(self._items)


class _FakePhoneme:
    def __init__(self, guid):
        self.guid = guid
        self.Guid = guid


class _FakeNCSegments:
    """Fake IPhNCSegments source natural class."""
    def __init__(self, guid, phoneme_refs):
        self.guid = guid
        self.Guid = guid
        self.SegmentsRC = _FakeCollection(phoneme_refs)


def _build_nc_execute_context(src_nc, src_phonemes, tgt_phonemes):
    """Build fake source + target handles for natural_classes_execute_action."""
    # Source handle
    source = MagicMock()
    source.NaturalClasses.GetAll.return_value = [src_nc]
    source.NaturalClasses.GetSyncableProperties.return_value = {}
    source.Phonemes.GetAll.return_value = src_phonemes

    # Target NC object: has a mutable SegmentsRC collection.
    tgt_nc = MagicMock()
    tgt_nc.SegmentsRC = _FakeCollection()

    # Factory returns the fake target NC.
    factory = MagicMock()
    factory.Create.return_value = tgt_nc

    # Target owner collection.
    owner_os = MagicMock()
    owner_os.Add.return_value = None

    # Cache chain.
    sl = MagicMock()
    sl.GetService.return_value = factory
    cache = MagicMock()
    cache.ServiceLocator = sl
    cache.LangProject.PhonologicalDataOA.NaturalClassesOS = owner_os

    target = MagicMock()
    target.Cache = cache
    target.NaturalClasses.ApplySyncableProperties.return_value = None
    target.Phonemes.GetAll.return_value = tgt_phonemes

    return source, target, tgt_nc


def _stub_lcm_nc_imports(monkeypatch):
    """Stub out SIL.LCModel NC interfaces so no real CLR is needed."""
    import sys

    class _PassthroughCast:
        """IPhNCSegments(obj) -> obj  (cast no-op for fakes)."""
        def __new__(cls, obj):
            return obj

    fake_lcm = MagicMock()
    fake_lcm.IPhNCSegmentsFactory = MagicMock()
    fake_lcm.IPhNCFeaturesFactory = MagicMock()
    fake_lcm.IPhNCSegments = _PassthroughCast
    # ICmObject(src_nc).ClassName => "PhNCSegments" for our fake.
    fake_lcm.ICmObject.side_effect = lambda obj: obj
    # Make sure obj.ClassName is "PhNCSegments" on our fakes
    # (handled by _FakeNCSegments not having ClassName; the except branch fires).

    original = sys.modules.get("SIL.LCModel")
    sys.modules["SIL.LCModel"] = fake_lcm
    return original, fake_lcm


def _restore_lcm(original):
    import sys
    if original is None:
        sys.modules.pop("SIL.LCModel", None)
    else:
        sys.modules["SIL.LCModel"] = original


def test_nc_execute_wires_segments_rc():
    """natural_classes_execute_action wires SegmentsRC with 2 target phonemes."""
    import sys

    p1_src = _FakePhoneme("ph-guid-1")
    p2_src = _FakePhoneme("ph-guid-2")
    p1_tgt = _FakePhoneme("ph-guid-1")
    p2_tgt = _FakePhoneme("ph-guid-2")

    src_nc = _FakeNCSegments("nc-guid-a", [p1_src, p2_src])
    source, target, tgt_nc = _build_nc_execute_context(
        src_nc, [p1_src, p2_src], [p1_tgt, p2_tgt]
    )

    action = MagicMock()
    action.source_guid = "nc-guid-a"

    ctx = _ctx(source, target)

    orig_sys = _fake_sys_guid(None)
    orig_lcm, _ = _stub_lcm_nc_imports(None)
    try:
        result = categories.natural_classes_execute_action(action, ctx, WSM, "test-tag")
    finally:
        _restore_sys_guid(orig_sys)
        _restore_lcm(orig_lcm)

    assert result is tgt_nc
    added_guids = [_._FakePhoneme__dict__ if hasattr(_, "_FakePhoneme__dict__") else _.guid
                   for _ in tgt_nc.SegmentsRC._items]
    # Simpler: check the items in SegmentsRC are p1_tgt and p2_tgt.
    assert p1_tgt in tgt_nc.SegmentsRC._items
    assert p2_tgt in tgt_nc.SegmentsRC._items
    assert len(tgt_nc.SegmentsRC._items) == 2


def test_nc_execute_raises_on_unresolved_phoneme():
    """natural_classes_execute_action raises RuntimeError when a source phoneme
    GUID has no counterpart on the target side."""
    import sys

    p1_src = _FakePhoneme("ph-guid-1")
    p2_src = _FakePhoneme("ph-guid-2")   # this one is NOT on target
    p1_tgt = _FakePhoneme("ph-guid-1")   # only ph-guid-1 on target

    src_nc = _FakeNCSegments("nc-guid-b", [p1_src, p2_src])
    source, target, tgt_nc = _build_nc_execute_context(
        src_nc, [p1_src, p2_src], [p1_tgt]  # tgt missing ph-guid-2
    )

    action = MagicMock()
    action.source_guid = "nc-guid-b"

    ctx = _ctx(source, target)

    orig_sys = _fake_sys_guid(None)
    orig_lcm, _ = _stub_lcm_nc_imports(None)
    try:
        with pytest.raises(RuntimeError) as exc_info:
            categories.natural_classes_execute_action(action, ctx, WSM, "test-tag")
    finally:
        _restore_sys_guid(orig_sys)
        _restore_lcm(orig_lcm)

    msg = str(exc_info.value)
    assert "ph-guid-2" in msg, f"Expected missing GUID in error: {msg}"
    assert "nc-guid-b" in msg, f"Expected NC GUID in error: {msg}"
