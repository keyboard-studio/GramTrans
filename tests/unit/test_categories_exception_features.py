"""Unit tests for exception_features leaf-category functions.

Covers:
- dependencies() returns empty tuple
- plan_action() with malformed piece yields UNSUPPORTED_LCM_TYPE skip
- plan_action() already-wired yields ALREADY_PRESENT_BY_GUID skip
- plan_action() new wiring yields PlannedAction with compound guid
- enumerate_source() yields (pos_guid, val_obj) pairs
- execute_action() is LCM-bound — integration only

Exception features in FLEx are IFsSymFeatVal references wired into
IPartOfSpeech.ExceptionFeaturesOC.  The piece here is a
(pos_guid_str, sym_feat_val_obj) tuple.
"""
from __future__ import annotations

import pytest

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


# ============================================================================
# Fake objects
# ============================================================================

class _FakeVal:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _FakePOS:
    def __init__(self, guid: str, exception_vals=()) -> None:
        self.guid = guid
        self.ExceptionFeaturesOC = list(exception_vals)

    @property
    def concrete(self):
        return self


class _FakePOSOps:
    def __init__(self, poses=()) -> None:
        self._poses = list(poses)

    def GetAll(self, recursive=True):
        return list(self._poses)


class _FakeProject:
    def __init__(self, name: str, poses=()) -> None:
        self.name = name
        self.POS = _FakePOSOps(poses)

    def ProjectName(self):
        return self.name


def _ctx(source, target) -> RunContext:
    return RunContext(
        source_handle=source,
        source_project_name="SrcProj",
        source_project_path="/src",
        target_handle=target,
        target_project_name="TgtProj",
        target_project_path="/tgt",
        run_id="GT-20260620-010000",
        started_at="2026-06-20T01:00:00",
    )


_BUNDLE = categories.for_category(GrammarCategory.EXCEPTION_FEATURES)


# ============================================================================
# Monkeypatch LCM casts
# ============================================================================

import gramtrans.Lib.categories as _cat_mod
import sys
import types


@pytest.fixture(autouse=True)
def _patch_lcm_cast(monkeypatch):
    monkeypatch.setattr(_cat_mod, "_guid_str_from", lambda obj: str(getattr(obj, "guid", "")).lower())

    class _FakeIPartOfSpeech:
        def __new__(cls, obj):
            return obj

    class _FakeICmObject:
        def __new__(cls, obj):
            return obj

    fake_lcm = types.ModuleType("SIL.LCModel")
    fake_lcm.IPartOfSpeech = _FakeIPartOfSpeech
    fake_lcm.ICmObject = _FakeICmObject
    sys.modules.setdefault("SIL", types.ModuleType("SIL"))
    original = sys.modules.get("SIL.LCModel")
    sys.modules["SIL.LCModel"] = fake_lcm
    yield
    if original is None:
        sys.modules.pop("SIL.LCModel", None)
    else:
        sys.modules["SIL.LCModel"] = original


# ============================================================================
# Tests
# ============================================================================

def test_dependencies_returns_empty_tuple() -> None:
    piece = ("pos-aaa", _FakeVal("val-bbb"))
    assert tuple(_BUNDLE["dependencies"](piece=piece)) == ()


def test_plan_action_malformed_piece_yields_unsupported_lcm_type_skip() -> None:
    """Non-tuple piece → UNSUPPORTED_LCM_TYPE skip (robust error path)."""
    result = _BUNDLE["plan_action"](piece="not-a-tuple", context=object(), ws_mapping=WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.UNSUPPORTED_LCM_TYPE


def test_plan_action_new_wiring_yields_planned_action() -> None:
    val = _FakeVal("v-001")
    pos = _FakePOS("p-001", exception_vals=())
    src = _FakeProject("src", poses=(pos,))
    tgt = _FakeProject("tgt", poses=())
    ctx = _ctx(src, tgt)

    piece = ("p-001", val)
    result = _BUNDLE["plan_action"](piece=piece, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.category == GrammarCategory.EXCEPTION_FEATURES
    # compound guid encodes both pos and val
    assert "p-001" in result.source_guid
    assert "v-001" in result.source_guid
    assert "::" in result.source_guid


def test_plan_action_already_wired_yields_already_present_skip() -> None:
    val = _FakeVal("v-002")
    pos_src = _FakePOS("p-002", exception_vals=(val,))
    src = _FakeProject("src", poses=(pos_src,))
    tgt_val = _FakeVal("v-002")
    tgt_pos = _FakePOS("p-002", exception_vals=(tgt_val,))
    tgt = _FakeProject("tgt", poses=(tgt_pos,))
    ctx = _ctx(src, tgt)

    piece = ("p-002", val)
    result = _BUNDLE["plan_action"](piece=piece, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID


def test_enumerate_source_yields_pos_guid_val_tuples() -> None:
    v1 = _FakeVal("v-100")
    v2 = _FakeVal("v-101")
    pos = _FakePOS("p-010", exception_vals=(v1, v2))
    src = _FakeProject("src", poses=(pos,))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)
    sel = Selection(categories={GrammarCategory.EXCEPTION_FEATURES: True})

    items = list(_BUNDLE["enumerate_source"](context=ctx, selection=sel))
    assert len(items) == 2
    pos_guids = [t[0] for t in items]
    val_objs = [t[1] for t in items]
    assert all(g == "p-010" for g in pos_guids)
    assert v1 in val_objs
    assert v2 in val_objs


def test_enumerate_source_empty_when_no_poses() -> None:
    src = _FakeProject("src", poses=())
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)
    sel = Selection(categories={GrammarCategory.EXCEPTION_FEATURES: True})

    items = list(_BUNDLE["enumerate_source"](context=ctx, selection=sel))
    assert items == []


@pytest.mark.integration
def test_execute_action_requires_lcm() -> None:
    pytest.skip("LCM required; run as integration test with FlexTools host.")
