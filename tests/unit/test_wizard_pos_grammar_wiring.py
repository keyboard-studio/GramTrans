"""fix/wizard-pos-grammar-wiring -- engine-level proof.

Companion to the wizard-plan folding tests in test_wizard_page_flow.py.

These tests prove the two engine behaviours the wizard fix relies on:

(a) When a Selection flags POS + carries pos_picks (as the fixed
    _compute_wizard_plan now produces from the Skeleton page), the
    verb-vertical POS closure walks EXACTLY those POSes -- so the plan
    reports ">0 source POS" and emits a POS action, instead of the buggy
    "closure over 0 source POS(es)".  With AFFIXES-only (the pre-fix
    Selection), the closure walks 0 POS.

(b) _resolve_target_pos returns a real target POS (not None) once that POS
    is present in the target -- so affix/stem MSAs wire to a part-of-speech
    instead of being created with None ("no grammatical info").

Reuses the minimal duck-typed fakes from test_closure_off_skip.py.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib import preview as preview_mod
from gramtrans.Lib import categories as categories_mod
from gramtrans.Lib.models import GrammarCategory, RunContext, Selection, WSMapping
from gramtrans.Lib.preview import build_run_plan, _select_source_poses


# ---------------------------------------------------------------------------
# Minimal fakes (same shapes as test_closure_off_skip.py)
# ---------------------------------------------------------------------------

class _POS:
    def __init__(self, guid: str) -> None:
        self.guid = guid

    @property
    def concrete(self):
        return self


class _POSOps:
    def __init__(self, verb=None) -> None:
        self._verb = verb

    def GetAll(self, recursive=False):  # noqa: N802
        return [self._verb] if self._verb is not None else []

    def GetSyncableProperties(self, pos):  # noqa: N802
        return {}

    def GetAffixSlots(self, pos):  # noqa: N802
        return []


class _MorphRulesOps:
    def GetAllAffixTemplatesForPOS(self, pos):  # noqa: N802
        return []

    def GetSyncableProperties(self, tpl):  # noqa: N802
        return {}


class _Project:
    def __init__(self, name, verb=None) -> None:
        self.name = name
        self.POS = _POSOps(verb=verb)
        self.MorphRules = _MorphRulesOps()

    def ProjectName(self):  # noqa: N802
        return self.name


@pytest.fixture
def _patch_lcm(monkeypatch):
    monkeypatch.setattr(preview_mod, "_guid_str", lambda obj: obj.guid)
    monkeypatch.setattr(
        preview_mod, "_unwrap",
        lambda obj: obj.concrete if hasattr(obj, "concrete") else obj,
    )


def _ctx(src, tgt) -> RunContext:
    return RunContext(
        source_handle=src,
        source_project_name="Src",
        source_project_path="/src",
        target_handle=tgt,
        target_project_name="Tgt",
        target_project_path="/tgt",
        run_id="GT-20260706-120000",
        started_at="2026-07-06T12:00:00",
    )


# ---------------------------------------------------------------------------
# (a) POS closure runs over the picked POS, not 0
# ---------------------------------------------------------------------------

class TestPosClosureWalksPickedPos:
    def test_pos_flagged_with_pos_picks_walks_that_pos(self, _patch_lcm):
        """Selection{POS:True, pos_picks={verb-1}} => closure walks that POS."""
        verb = _POS("verb-1")
        src = _Project("src", verb=verb)
        sel = Selection(
            categories={GrammarCategory.POS: True},
            pos_picks=frozenset({"verb-1"}),
        )
        walked = _select_source_poses(src, sel)
        assert [p.guid for p in walked] == ["verb-1"]

    def test_affixes_only_walks_zero_pos(self, _patch_lcm):
        """The BUGGY pre-fix Selection (AFFIXES on, POS absent) walks 0 POS --
        reproducing 'verb-vertical closure over 0 source POS(es)'."""
        verb = _POS("verb-1")
        src = _Project("src", verb=verb)
        sel = Selection(categories={GrammarCategory.AFFIXES: True})
        assert _select_source_poses(src, sel) == []

    def test_plan_emits_pos_action_for_picked_pos(self, _patch_lcm):
        """End-to-end: the fixed Selection yields a POS action in the plan (the
        POS gets created in the target so downstream MSAs can wire to it)."""
        verb = _POS("verb-1")
        src = _Project("src", verb=verb)
        tgt = _Project("tgt")  # target lacks the POS
        sel = Selection(
            categories={GrammarCategory.POS: True},
            pos_picks=frozenset({"verb-1"}),
        )
        plan = build_run_plan(_ctx(src, tgt), sel, WSMapping(entries=()), src, tgt)
        pos_actions = [a for a in plan.actions if a.category == GrammarCategory.POS]
        assert len(pos_actions) == 1
        assert pos_actions[0].source_guid == "verb-1"


# ---------------------------------------------------------------------------
# (b) affix MSAs resolve to a real target POS, not None
# ---------------------------------------------------------------------------

class TestResolveTargetPos:
    def test_resolves_when_pos_present_in_target(self):
        """Once the POS closure has created the POS in the target,
        _resolve_target_pos returns it (MSA wires to a real POS)."""
        tgt = _Project("tgt", verb=_POS("verb-1"))
        resolved = categories_mod._resolve_target_pos(tgt, "verb-1")
        assert resolved is not None
        assert categories_mod._guid_str_from(resolved) == "verb-1"

    def test_returns_none_when_pos_absent(self):
        """The buggy state: POS never created in target => MSA would be built
        with None ('no grammatical info')."""
        tgt = _Project("tgt")  # no POS
        assert categories_mod._resolve_target_pos(tgt, "verb-1") is None
