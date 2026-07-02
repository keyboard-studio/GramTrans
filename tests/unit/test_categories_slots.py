"""Unit tests for Phase 3c US2 slots leaf-category functions (T032-T033).

Slots are IMoInflAffixSlot owned by IPartOfSpeech.AffixSlotsOC. Covers:
- T032 enumerate_source + plan_action: one PlannedAction per source slot,
  GUID preserved (intended_target_guid == source GUID), owner POS resolvable.
- T033 plan_action collision guard: slot GUID already in target →
  Skip(ALREADY_PRESENT_BY_GUID) per FR-334.

execute_action is LCM-bound (IMoInflAffixSlotFactory); the live creation +
owner-attach is exercised by the integration suite (T041 / Scenario A).
"""
from __future__ import annotations

import sys
import types

import pytest

# Phase 3c leaf-dispatch for slots (T029/T032-T033) is still stubbed in
# categories.py (`raise NotImplementedError("Phase 3c T029")`). These are
# red-by-design TDD tests for that pending work (spec 007); mark xfail so the
# trunk suite stays green and they auto-flip to passing once implemented.
pytestmark = pytest.mark.xfail(
    reason="Phase 3c T029 slots leaf-dispatch not yet implemented (spec 007)",
    raises=NotImplementedError,
    strict=False,
)

from gramtrans.Lib import categories
import gramtrans.Lib.categories as _cat_mod
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
# Fakes (duck-typed POS / slot surfaces)
# ============================================================================

class _FakeSlot:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _FakePOS:
    def __init__(self, guid: str, slots=()) -> None:
        self.guid = guid
        self.AffixSlotsOC = list(slots)

    @property
    def concrete(self):
        return self


class _FakePOSOps:
    def __init__(self, poses=()) -> None:
        self._poses = list(poses)

    def GetAll(self, recursive=True):
        return list(self._poses)


class _FakeProject:
    def __init__(self, poses=()) -> None:
        self.POS = _FakePOSOps(poses)


def _ctx(source, target) -> RunContext:
    return RunContext(
        source_handle=source,
        source_project_name="Src",
        source_project_path="/src",
        target_handle=target,
        target_project_name="Tgt",
        target_project_path="/tgt",
        run_id="GT-20260628-010000",
        started_at="2026-06-28T01:00:00",
    )


_BUNDLE = categories.for_category(GrammarCategory.SLOTS)


@pytest.fixture(autouse=True)
def _patch_lcm_cast(monkeypatch):
    """Identity-cast IPartOfSpeech + guid-from-attr so fakes work host-free."""
    monkeypatch.setattr(
        _cat_mod, "_guid_str_from",
        lambda obj: str(getattr(obj, "guid", "")).lower(),
    )

    class _Identity:
        def __new__(cls, obj):
            return obj

    fake_lcm = types.ModuleType("SIL.LCModel")
    fake_lcm.IPartOfSpeech = _Identity
    fake_lcm.ICmObject = _Identity
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
    assert tuple(_BUNDLE["dependencies"](piece=_FakeSlot("s-1"))) == ()


def test_enumerate_source_yields_all_slots_across_poses() -> None:
    s1 = _FakeSlot("slot-1")
    s2 = _FakeSlot("slot-2")
    pos_a = _FakePOS("pos-verb", slots=(s1,))
    pos_b = _FakePOS("pos-noun", slots=(s2,))
    src = _FakeProject(poses=(pos_a, pos_b))
    ctx = _ctx(src, _FakeProject())

    items = list(_BUNDLE["enumerate_source"](ctx, None))
    assert {i.guid for i in items} == {"slot-1", "slot-2"}


def test_slot_creation_under_pos() -> None:
    """T032: 1 source slot under Verb POS, target has Verb POS already →
    plan_action emits a GUID-preserving PlannedAction (intended == source)."""
    slot = _FakeSlot("slot-verb-1")
    src_pos = _FakePOS("pos-verb", slots=(slot,))
    src = _FakeProject(poses=(src_pos,))
    # Target already has the owner POS but NOT the slot.
    tgt = _FakeProject(poses=(_FakePOS("pos-verb", slots=()),))
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=slot, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.category == GrammarCategory.SLOTS
    assert result.source_guid == "slot-verb-1"
    # GUID preserved (E8: slots created via Create(Guid)).
    assert result.intended_target_guid == "slot-verb-1"


def test_slot_collision_already_present_by_guid() -> None:
    """T033: slot GUID already under a target POS → Skip(ALREADY_PRESENT_BY_GUID)."""
    slot = _FakeSlot("slot-dup")
    src_pos = _FakePOS("pos-verb", slots=(slot,))
    src = _FakeProject(poses=(src_pos,))
    tgt = _FakeProject(poses=(_FakePOS("pos-verb", slots=(_FakeSlot("slot-dup"),)),))
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=slot, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    assert result.source_guid == "slot-dup"


@pytest.mark.integration
def test_slot_execute_requires_lcm() -> None:
    pytest.skip("LCM required; live slot creation covered by integration suite.")
