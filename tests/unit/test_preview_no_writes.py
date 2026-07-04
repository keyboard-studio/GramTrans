"""T029: Preview Mode produces ZERO mutations against fakes (SC-006, Principle III).

Builds a fake source/target pair where every write attempt against the target
is recorded by a sentinel. `Lib/preview.build_run_plan` walks the source closure
and produces a `RunPlan` — and the recorder MUST be empty when it returns.

This is the unit-level guarantee that backs FR-014 (Preview = default) and
SC-006 (Preview Mode zero writes). The integration-level analog runs against
a live target snapshot (T081).
"""
from __future__ import annotations

from typing import Iterable, List

import pytest

from gramtrans.Lib import preview as preview_mod
from gramtrans.Lib.models import (
    GrammarCategory,
    RunContext,
    Selection,
    WSMapping,
)
from gramtrans.Lib.preview import build_run_plan


# ============================================================================
# Recording fakes
# ============================================================================

class _WriteRecorder:
    """Shared bucket — every fake mutating method appends `(method, *args)`."""

    def __init__(self) -> None:
        self.writes: List[tuple] = []

    def record(self, label: str, *args) -> None:
        self.writes.append((label, args))


class _GuardedField:
    """A trap that raises if anyone tries to read/write 'forbidden' methods."""

    def __init__(self, recorder: _WriteRecorder, label: str) -> None:
        self._rec = recorder
        self._label = label

    def __getattr__(self, name: str):
        self._rec.record(f"{self._label}.{name}", "ATTR-ACCESS")
        raise AssertionError(
            f"preview reached forbidden field {self._label}.{name}"
        )


class _FakeSlot:
    def __init__(self, guid: str, name: str = "slot") -> None:
        self.guid = guid
        self._name = name


class _FakeName:
    def __init__(self, name: str) -> None:
        self.BestAnalysisAlternative = type("S", (), {"Text": name})()


class _FakeTemplate:
    def __init__(self, guid: str, prefix=(), suffix=(), pro=(), enc=()) -> None:
        self.guid = guid
        self.prefix_slots = prefix
        self.suffix_slots = suffix
        self.proclitic_slots = pro
        self.enclitic_slots = enc

    @property
    def concrete(self):
        return self


class _FakePOS:
    def __init__(self, guid: str) -> None:
        self.guid = guid

    @property
    def concrete(self):
        return self


class _FakePOSOps:
    def __init__(self, verb=None, all_=()) -> None:
        self._verb = verb
        self._all = all_

    def Find(self, name: str):  # noqa: N802 — matches flexicon API
        return self._verb if name == "Verb" else None

    def GetAll(self, recursive: bool = False):  # noqa: N802
        # When the fake has a verb set, include it in GetAll so the
        # multi-POS walker's _select_source_poses finds it.
        if self._verb is not None and not self._all:
            return [self._verb]
        return list(self._all)

    def GetSyncableProperties(self, pos):  # noqa: N802
        return {}

    def GetAffixSlots(self, pos):  # noqa: N802
        return []


class _FakeMorphRulesOps:
    def __init__(self, templates=()) -> None:
        self._tpls = list(templates)

    def GetAllAffixTemplatesForPOS(self, pos):  # noqa: N802
        return list(self._tpls)

    def GetSyncableProperties(self, tpl):  # noqa: N802
        return {}


class _FakeProject:
    """Pretends to be a flexicon FLExProject for the preview walker.

    Each instance gets its own POS/MorphRules accessor objects so source and
    target are distinct identities (RunContext FR-019 check).
    """

    def __init__(self, name: str, verb=None, templates=(), all_pos=()) -> None:
        self.name = name
        self.POS = _FakePOSOps(verb=verb, all_=all_pos)
        self.MorphRules = _FakeMorphRulesOps(templates=templates)
        # Anything that tries to access a non-existent method should raise —
        # in particular, ApplySyncableProperties / set_String / OS.Add etc.
        # are NOT defined on this fake; AttributeError would surface if
        # preview tried to call them (which it MUST NOT).

    def ProjectName(self) -> str:  # noqa: N802
        return self.name


# ============================================================================
# Monkeypatch the LCM-aware helpers in preview.py to use our fake attributes
# ============================================================================

@pytest.fixture
def _patch_preview_lcm_helpers(monkeypatch):
    """Replace preview.py's LCM-cast helpers with attribute lookups so the
    fakes above can stand in for flexicon objects."""
    monkeypatch.setattr(preview_mod, "_guid_str", lambda obj: obj.guid)
    monkeypatch.setattr(preview_mod, "_unwrap", lambda obj: obj.concrete if hasattr(obj, "concrete") else obj)
    monkeypatch.setattr(preview_mod, "_slot_name", lambda slot: getattr(slot, "_name", "anon"))


# ============================================================================
# Tests
# ============================================================================

def _ctx(source, target) -> RunContext:
    return RunContext(
        source_handle=source,
        source_project_name="FakeSource",
        source_project_path="/fake/src",
        target_handle=target,
        target_project_name="FakeTarget",
        target_project_path="/fake/tgt",
        run_id="GT-20260619-140000",
        started_at="2026-06-19T14:00:00",
    )


def _selection() -> Selection:
    return Selection(
        categories={
            GrammarCategory.POS: True,
            GrammarCategory.AFFIX_TEMPLATES: True,
            GrammarCategory.SLOTS: True,
        },
        include_closure=True,
    )


def test_empty_source_yields_empty_plan_and_no_writes(_patch_preview_lcm_helpers):
    """Edge case: source with no Verb POS produces an empty plan; the
    recorder MUST observe zero writes."""
    rec = _WriteRecorder()
    src = _FakeProject("src", verb=None)
    tgt = _FakeProject("tgt", verb=None)
    plan = build_run_plan(_ctx(src, tgt), _selection(), WSMapping(entries=()), src, tgt)
    assert plan.actions == ()
    assert plan.skips == ()
    assert rec.writes == []


def test_populated_source_empty_target_produces_actions_but_no_writes(_patch_preview_lcm_helpers):
    """Realistic case: source has Verb + template + 2 slots; target is empty.
    Preview emits PlannedActions for all of them — and recorder stays empty."""
    rec = _WriteRecorder()
    src_verb = _FakePOS("verb-guid-1")
    src_slot_a = _FakeSlot("slot-a", "AGR")
    src_slot_b = _FakeSlot("slot-b", "TNS")
    src_tpl = _FakeTemplate("tpl-1", prefix=(src_slot_a,), suffix=(src_slot_b,))
    src = _FakeProject("src", verb=src_verb, templates=(src_tpl,))
    tgt = _FakeProject("tgt", verb=None, templates=(), all_pos=())

    plan = build_run_plan(_ctx(src, tgt), _selection(), WSMapping(entries=()), src, tgt)

    # POS + 1 template + 2 slots = 4 actions; 0 skips.
    assert len(plan.actions) == 4
    assert plan.skips == ()
    cats = [a.category for a in plan.actions]
    assert cats.count(GrammarCategory.POS) == 1
    assert cats.count(GrammarCategory.AFFIX_TEMPLATES) == 1
    assert cats.count(GrammarCategory.SLOTS) == 2

    # The crown jewel: no writes against the target during planning.
    assert rec.writes == []


def test_target_already_has_guids_emits_skips_not_actions(_patch_preview_lcm_helpers):
    """Source pieces whose GUIDs already exist in the target are SKIPS, not
    actions — and still no writes."""
    rec = _WriteRecorder()
    src_verb = _FakePOS("verb-guid-1")
    src = _FakeProject("src", verb=src_verb, templates=())
    # Target's POS list contains the same verb GUID.
    tgt_verb = _FakePOS("verb-guid-1")
    tgt = _FakeProject("tgt", verb=None, all_pos=(tgt_verb,))

    plan = build_run_plan(_ctx(src, tgt), _selection(), WSMapping(entries=()), src, tgt)

    assert plan.actions == ()
    assert len(plan.skips) == 1
    assert plan.skips[0].category == GrammarCategory.POS
    assert plan.skips[0].source_guid == "verb-guid-1"
    assert rec.writes == []


def test_fr019_same_project_handle_refused() -> None:
    """RunContext rejects identical source/target handles (FR-019)."""
    p = _FakeProject("ambiguous")
    with pytest.raises(ValueError, match="FR-019"):
        _ctx(p, p)
