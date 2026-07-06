"""Phase 1 planner — `selection.enable_overwrite=True` reclassifies
ALREADY_PRESENT_BY_GUID items as PlannedOverwrites (FR-101 / FR-108)."""
from __future__ import annotations

import pytest

# Phase-1 overwrite promotion here runs through the verb-vertical POS-closure
# planner, which was superseded by leaf-dispatch on 2026-07-06 (double-dispatch
# GUID-collision fix). Overwrite/UPDATE semantics now live on the leaf-dispatch
# + disposition path (feature 022). Follow-up: migrate these invariants to
# leaf-dispatch coverage and delete the verb-vertical code + these tests.
pytestmark = pytest.mark.xfail(
    reason="verb-vertical Phase-1 overwrite planner superseded by leaf-dispatch (2026-07-06)",
    strict=False,
)

from gramtrans.Lib import preview as preview_mod
from gramtrans.Lib.models import (
    GrammarCategory,
    PlannedOverwrite,
    RunContext,
    Selection,
    SkipReason,
    WSMapping,
)
from gramtrans.Lib.preview import build_run_plan


# ============================================================================
# Minimal fakes — reuse the shape from test_preview_no_writes.py
# ============================================================================

class _Slot:
    def __init__(self, guid, name="slot"):
        self.guid = guid
        self._name = name


class _Template:
    def __init__(self, guid, prefix=(), suffix=(), pro=(), enc=()):
        self.guid = guid
        self.prefix_slots = prefix
        self.suffix_slots = suffix
        self.proclitic_slots = pro
        self.enclitic_slots = enc

    @property
    def concrete(self):
        return self


class _POS:
    def __init__(self, guid):
        self.guid = guid

    @property
    def concrete(self):
        return self


class _POSOps:
    def __init__(self, verb=None, all_pos=()):
        self._verb = verb
        self._all = list(all_pos)

    def Find(self, name):  # noqa: N802
        return self._verb if name == "Verb" else None

    def GetAll(self, recursive=False):  # noqa: N802
        if self._verb is not None and not self._all:
            return [self._verb]
        return self._all

    def GetSyncableProperties(self, pos):  # noqa: N802
        return {}

    def GetAffixSlots(self, pos):  # noqa: N802
        return []


class _MorphRulesOps:
    def __init__(self, templates=()):
        self._tpls = list(templates)

    def GetAllAffixTemplatesForPOS(self, pos):  # noqa: N802
        return self._tpls

    def GetSyncableProperties(self, tpl):  # noqa: N802
        return {}


class _Project:
    def __init__(self, name, verb=None, templates=(), all_pos=()):
        self.name = name
        self.POS = _POSOps(verb=verb, all_pos=all_pos)
        self.MorphRules = _MorphRulesOps(templates=templates)


@pytest.fixture
def _patch_lcm(monkeypatch):
    monkeypatch.setattr(preview_mod, "_guid_str", lambda obj: obj.guid)
    monkeypatch.setattr(preview_mod, "_unwrap", lambda obj: obj.concrete if hasattr(obj, "concrete") else obj)
    monkeypatch.setattr(preview_mod, "_slot_name", lambda slot: getattr(slot, "_name", "anon"))


def _ctx(src, tgt) -> RunContext:
    return RunContext(
        source_handle=src, source_project_name="Src", source_project_path="/s",
        target_handle=tgt, target_project_name="Tgt", target_project_path="/t",
        run_id="GT-20260620-010000", started_at="2026-06-20T01:00:00",
    )


# ============================================================================
# Phase 0 (default) behavior: enable_overwrite=False → skip, no overwrites
# ============================================================================

def test_phase0_default_target_has_guid_emits_skip_not_overwrite(_patch_lcm):
    """Backward compat: Phase 0 default behavior is preserved."""
    verb = _POS("verb-1")
    tpl = _Template("tpl-1", prefix=(_Slot("s-a", "AGR"),))
    src = _Project("src", verb=verb, templates=(tpl,))

    # Target has the same POS GUID → Phase 0 emits Skip(ALREADY_PRESENT_BY_GUID)
    tgt_verb = _POS("verb-1")
    tgt = _Project("tgt", verb=None, all_pos=(tgt_verb,))

    sel = Selection(
        categories={GrammarCategory.POS: True, GrammarCategory.AFFIX_TEMPLATES: True, GrammarCategory.SLOTS: True},
        include_closure=True,
        enable_overwrite=False,  # Phase 0 default
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)
    assert plan.overwrites == ()
    pos_skips = [s for s in plan.skips if s.category == GrammarCategory.POS]
    assert len(pos_skips) == 1
    assert pos_skips[0].reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ============================================================================
# Phase 1 behavior: enable_overwrite=True → PlannedOverwrite, no skip
# ============================================================================

def test_phase1_enable_overwrite_promotes_already_present_pos_to_overwrite(_patch_lcm):
    verb = _POS("verb-1")
    src = _Project("src", verb=verb, templates=())
    tgt_verb = _POS("verb-1")
    tgt = _Project("tgt", verb=None, all_pos=(tgt_verb,))

    sel = Selection(
        categories={GrammarCategory.POS: True},
        include_closure=True,
        enable_overwrite=True,  # Phase 1 flag
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)

    # No SKIP for the POS — it was reclassified
    pos_skips = [s for s in plan.skips if s.category == GrammarCategory.POS]
    assert pos_skips == []

    # One PlannedOverwrite for the POS
    pos_overwrites = [o for o in plan.overwrites if o.category == GrammarCategory.POS]
    assert len(pos_overwrites) == 1
    assert pos_overwrites[0].source_guid == "verb-1"
    assert pos_overwrites[0].target_guid == "verb-1"
    assert pos_overwrites[0].match_via == "guid"


def test_phase1_enable_overwrite_does_not_change_add_path(_patch_lcm):
    """Items that DON'T exist in target still get PlannedActions, not overwrites."""
    verb = _POS("verb-fresh")
    src = _Project("src", verb=verb, templates=())
    tgt = _Project("tgt", verb=None, all_pos=())  # target empty

    sel = Selection(
        categories={GrammarCategory.POS: True},
        include_closure=True,
        enable_overwrite=True,
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)
    assert len(plan.actions) == 1
    assert plan.actions[0].category == GrammarCategory.POS
    assert plan.overwrites == ()
    assert plan.skips == ()


def test_phase1_overwrite_propagates_to_templates_and_slots(_patch_lcm):
    """Mix: POS, template, and one slot already in target → 3 overwrites."""
    verb = _POS("verb-1")
    tpl = _Template("tpl-1", prefix=(_Slot("s-a", "AGR"),), suffix=(_Slot("s-b", "TNS"),))
    src = _Project("src", verb=verb, templates=(tpl,))

    # Target has POS, template, and ONE matching slot (s-a). s-b is missing.
    tgt_verb = _POS("verb-1")
    tgt_tpl = _Template("tpl-1", prefix=(_Slot("s-a", "AGR"),))

    class _TargetPOSOps(_POSOps):
        def GetAffixSlots(self, pos):  # noqa: N802
            return [_Slot("s-a", "AGR")]

    class _TargetMorphRulesOps(_MorphRulesOps):
        def GetAllAffixTemplatesForPOS(self, pos):  # noqa: N802
            return [tgt_tpl]

    tgt = _Project("tgt", verb=None, all_pos=(tgt_verb,))
    tgt.POS = _TargetPOSOps(verb=None, all_pos=(tgt_verb,))
    tgt.MorphRules = _TargetMorphRulesOps()

    sel = Selection(
        categories={GrammarCategory.POS: True, GrammarCategory.AFFIX_TEMPLATES: True, GrammarCategory.SLOTS: True},
        include_closure=True,
        enable_overwrite=True,
    )
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)

    # POS + Template + s-a overwrite; s-b adds (was missing from target)
    overwrite_cats = sorted([o.category.value for o in plan.overwrites])
    action_cats = sorted([a.category.value for a in plan.actions])
    assert "pos" in overwrite_cats
    assert "affix_templates" in overwrite_cats
    assert "slots" in overwrite_cats  # s-a
    assert action_cats == ["slots"]  # s-b


def test_phase1_run_report_has_overwritten_count(_patch_lcm):
    """RunReport.build_from_plan counts overwrites per category (FR-110)."""
    from gramtrans.Lib.models import RunMode
    from gramtrans.Lib.report import RunReport
    verb = _POS("verb-1")
    src = _Project("src", verb=verb)
    tgt = _Project("tgt", verb=None, all_pos=(_POS("verb-1"),))
    sel = Selection(categories={GrammarCategory.POS: True}, enable_overwrite=True)
    plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)
    report = RunReport.build_from_plan(plan, RunMode.PREVIEW)
    assert report.per_category[GrammarCategory.POS].overwritten == 1
    assert report.per_category[GrammarCategory.POS].added == 0
    assert report.per_category[GrammarCategory.POS].skipped == 0
