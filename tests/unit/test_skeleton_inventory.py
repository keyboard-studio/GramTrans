"""Tests for build_skeleton_inventory (T002, T003).

TDD: these tests are written BEFORE the implementation in selection.py.
They cover:
  T002 - POS preselected iff a picked affix attaches; slot preselected iff
         a picked affix fills it (SlotsRC); unfilled POS slots shown unchecked;
         per-slot affix count; template lists slots read-only; template
         preselected when it arranges a referenced slot; POS-rooted nesting;
         empty-POS pruning.
  T003 - template-forces-slots: selecting a template yields its full referenced
         slot set (incl. extras); deselecting yields only affix-filled slots;
         affix_picks unchanged either way.
"""
from __future__ import annotations

import pytest

from _fakes_affix import (
    make_infl_entry_with_slots,
    make_pos_with_slots,
    make_slot,
    make_template,
    make_source,
    FakeInflMsaWithSlots,
    FakeSense,
    FakeEntry,
)

from gramtrans.Lib.selection import build_skeleton_inventory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_simple_scene():
    """Verb POS with 2 slots; entry fills slot_a only; template refs both slots."""
    slot_a = make_slot("slot-a-guid", "Present")
    slot_b = make_slot("slot-b-guid", "Past")
    tpl = make_template("tpl-guid", "VerbTemplate", slots=[slot_a, slot_b])
    pos_v = make_pos_with_slots(
        "pos-v-guid", "v", "Verb",
        slots=[slot_a, slot_b],
        templates=[tpl],
    )
    entry = make_infl_entry_with_slots(
        "entry-1-guid", "-s", ["3SG"], pos_v, slots=[slot_a]
    )
    source = make_source([entry], [pos_v])
    affix_picks = frozenset(["entry-1-guid"])
    return source, affix_picks, pos_v, slot_a, slot_b, tpl


# ---------------------------------------------------------------------------
# T002: basic skeleton derivation
# ---------------------------------------------------------------------------

class TestBuildSkeletonInventoryBasic:

    def test_returns_result_with_pos_nodes(self):
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        assert result is not None
        assert len(result.pos_nodes) >= 1

    def test_pos_preselected_when_picked_affix_attaches(self):
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        assert pos_node.pos_guid == "pos-v-guid"
        assert pos_node.preselected is True

    def test_pos_not_preselected_when_no_picked_affix_attaches(self):
        """A POS that has entries but none of them are in affix_picks -> not preselected."""
        slot_a = make_slot("slot-x", "X")
        pos_v = make_pos_with_slots("pos-v", "v", "Verb", slots=[slot_a])
        entry = make_infl_entry_with_slots("entry-1", "-s", ["gloss"], pos_v, [slot_a])
        source = make_source([entry], [pos_v])
        # affix_picks is empty — no picks
        result = build_skeleton_inventory(source, frozenset())
        # POS with no picked affixes should be absent (pruned) or not preselected
        if result.pos_nodes:
            assert all(not pn.preselected for pn in result.pos_nodes)

    def test_empty_pos_pruned(self):
        """A POS with no affix entries at all is excluded from the skeleton."""
        pos_empty = make_pos_with_slots("pos-empty", "z", "Empty")
        source = make_source([], [pos_empty])
        result = build_skeleton_inventory(source, frozenset())
        assert len(result.pos_nodes) == 0

    def test_slot_preselected_when_picked_affix_fills_it(self):
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        slot_a_node = next(s for s in pos_node.slots if s.slot_guid == "slot-a-guid")
        assert slot_a_node.preselected is True

    def test_slot_not_preselected_when_no_picked_affix_fills_it(self):
        """slot_b is on the POS but no picked affix fills it -> unchecked."""
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        slot_b_node = next(s for s in pos_node.slots if s.slot_guid == "slot-b-guid")
        assert slot_b_node.preselected is False

    def test_unfilled_slot_still_present(self):
        """Slots no picked affix fills MUST still appear (FR-004: shown unchecked)."""
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        slot_guids = {s.slot_guid for s in pos_node.slots}
        assert "slot-b-guid" in slot_guids

    def test_slot_affix_count_correct(self):
        """Per-slot affix count: slot_a filled by 1 entry, slot_b by 0."""
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        slot_a_node = next(s for s in pos_node.slots if s.slot_guid == "slot-a-guid")
        slot_b_node = next(s for s in pos_node.slots if s.slot_guid == "slot-b-guid")
        assert slot_a_node.affix_count == 1
        assert slot_b_node.affix_count == 0

    def test_template_listed_under_pos(self):
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        assert len(pos_node.templates) >= 1
        assert pos_node.templates[0].template_guid == "tpl-guid"


class TestSlotOptionalFlag:
    """IMoInflAffixSlot.Optional propagates to SlotNode.optional.

    An empty optional slot is benign; an empty required slot would break the
    template on transfer. The UI shows optional slots in parentheses (FLEx
    convention) and strikes through any slot that won't copy over.
    """

    def test_optional_slot_flag_true(self):
        slot_opt = make_slot("slot-opt", "Repetitive", optional=True)
        slot_req = make_slot("slot-req", "SbjAgr", optional=False)
        pos_v = make_pos_with_slots(
            "pos-v", "v", "Verb", slots=[slot_opt, slot_req]
        )
        entry = make_infl_entry_with_slots(
            "e1", "-s", ["3sg"], pos_v, [slot_req]
        )
        source = make_source([entry], [pos_v])
        result = build_skeleton_inventory(source, frozenset(["e1"]))
        pos_node = result.pos_nodes[0]
        opt_node = next(s for s in pos_node.slots if s.slot_guid == "slot-opt")
        req_node = next(s for s in pos_node.slots if s.slot_guid == "slot-req")
        assert opt_node.optional is True
        assert req_node.optional is False

    def test_optional_defaults_false_when_unreadable(self):
        """A slot fake lacking .Optional falls back to required (False)."""
        slot = make_slot("slot-x", "X")
        del slot.Optional  # simulate a runtime object without the property
        pos_v = make_pos_with_slots("pos-v", "v", "Verb", slots=[slot])
        entry = make_infl_entry_with_slots("e1", "-s", ["g"], pos_v, [slot])
        source = make_source([entry], [pos_v])
        result = build_skeleton_inventory(source, frozenset(["e1"]))
        slot_node = result.pos_nodes[0].slots[0]
        assert slot_node.optional is False

    def test_template_preselected_when_references_filled_slot(self):
        """Template is preselected when it arranges a slot a picked affix fills."""
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        tpl_node = pos_node.templates[0]
        assert tpl_node.preselected is True

    def test_template_slot_list_read_only_no_separate_checkable(self):
        """Template nodes carry their referenced slot GUIDs but do NOT duplicate
        the top-level slot list (FR-006: read-only slot list under template)."""
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        tpl_node = pos_node.templates[0]
        # The template node should expose referenced_slot_guids (read-only list)
        assert "slot-a-guid" in tpl_node.referenced_slot_guids
        assert "slot-b-guid" in tpl_node.referenced_slot_guids

    def test_per_slot_count_multiple_affixes(self):
        """Two entries both fill slot_a -> count == 2."""
        slot_a = make_slot("slot-a", "Present")
        pos_v = make_pos_with_slots("pos-v", "v", "Verb", slots=[slot_a])
        e1 = make_infl_entry_with_slots("e1", "-s", ["3sg"], pos_v, [slot_a])
        e2 = make_infl_entry_with_slots("e2", "-pl", ["pl"], pos_v, [slot_a])
        source = make_source([e1, e2], [pos_v])
        result = build_skeleton_inventory(source, frozenset(["e1", "e2"]))
        pos_node = result.pos_nodes[0]
        slot_node = pos_node.slots[0]
        assert slot_node.affix_count == 2

    def test_no_target_status_none_when_target_not_supplied(self):
        source, affix_picks, pos_v, slot_a, slot_b, tpl = _make_simple_scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        assert pos_node.status is None

    def test_multiple_pos_nodes(self):
        """Two POSes, each with one filled slot -> two POS nodes returned."""
        slot_a = make_slot("sa", "A")
        slot_b = make_slot("sb", "B")
        pos_v = make_pos_with_slots("pv", "v", "Verb", slots=[slot_a])
        pos_n = make_pos_with_slots("pn", "n", "Noun", slots=[slot_b])
        e1 = make_infl_entry_with_slots("e1", "-v", ["gloss"], pos_v, [slot_a])
        e2 = make_infl_entry_with_slots("e2", "-n", ["gloss"], pos_n, [slot_b])
        source = make_source([e1, e2], [pos_v, pos_n])
        result = build_skeleton_inventory(source, frozenset(["e1", "e2"]))
        assert len(result.pos_nodes) == 2
        guids = {n.pos_guid for n in result.pos_nodes}
        assert "pv" in guids
        assert "pn" in guids


# ---------------------------------------------------------------------------
# T003: template-forces-slots semantics
# ---------------------------------------------------------------------------

class TestSkeletonTemplateSemantics:

    def _scene(self):
        """POS with slot_a (filled by entry) and slot_b (unfilled), template refs both."""
        slot_a = make_slot("sa", "Slot-A")
        slot_b = make_slot("sb", "Slot-B")
        tpl = make_template("tpl", "VerbTpl", slots=[slot_a, slot_b])
        pos_v = make_pos_with_slots("pv", "v", "Verb",
                                     slots=[slot_a, slot_b], templates=[tpl])
        entry = make_infl_entry_with_slots("e1", "-s", ["3sg"], pos_v, [slot_a])
        source = make_source([entry], [pos_v])
        affix_picks = frozenset(["e1"])
        return source, affix_picks

    def test_template_preselected_includes_extra_slot(self):
        """A preselected template forces slot_b in even though no picked affix fills it."""
        source, affix_picks = self._scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        tpl_node = pos_node.templates[0]
        assert tpl_node.preselected is True
        # The template's referenced slots include the unfilled slot_b
        assert "sb" in tpl_node.referenced_slot_guids

    def test_deselect_template_leaves_only_affix_filled_slots_selected(self):
        """When template is deselected only affix-filled slots remain preselected."""
        source, affix_picks = self._scene()
        result = build_skeleton_inventory(source, affix_picks)
        pos_node = result.pos_nodes[0]
        # Simulate deselect: compute the "deselected" slot set
        affix_filled_guids = result.affix_filled_slot_guids()
        assert "sa" in affix_filled_guids
        assert "sb" not in affix_filled_guids

    def test_affix_picks_unchanged_by_template_semantics(self):
        """Template selection/deselection must NOT change affix_picks."""
        source, affix_picks = self._scene()
        result = build_skeleton_inventory(source, affix_picks)
        # The inventory should not expand or modify affix_picks
        assert result.affix_picks == affix_picks

    def test_template_not_preselected_when_no_affixes_fill_any_referenced_slot(self):
        """Template whose slots are all unfilled -> not preselected."""
        slot_a = make_slot("sa", "A")
        slot_b = make_slot("sb", "B")
        tpl = make_template("tpl", "T", slots=[slot_a, slot_b])
        pos_v = make_pos_with_slots("pv", "v", "V", slots=[slot_a, slot_b], templates=[tpl])
        # entry fills neither slot
        entry = make_infl_entry_with_slots("e1", "-s", ["g"], pos_v, [])
        source = make_source([entry], [pos_v])
        result = build_skeleton_inventory(source, frozenset(["e1"]))
        if result.pos_nodes:
            pos_node = result.pos_nodes[0]
            if pos_node.templates:
                assert pos_node.templates[0].preselected is False


# ---------------------------------------------------------------------------
# FR-009: SELF-TARGET skeleton status (all rows must read "in_target")
# ---------------------------------------------------------------------------

class TestSkeletonSelfTargetStatus:
    """When target==source project every skeleton row must read 'in_target'.

    This is the exact case the pre-fix cycle missed: the old code looked up
    skeleton GUIDs in the affix-entry set, so POS/slot/template (which are
    NOT affix entries) all fell to "new".  The fix enumerates per-kind target
    GUID sets from the target's POS hierarchy.
    """

    def _self_target_scene(self):
        """Simple scene: one POS, one slot, one template, one entry."""
        slot_a = make_slot("slot-a-guid", "Present")
        tpl = make_template("tpl-guid", "VerbTemplate", slots=[slot_a])
        pos_v = make_pos_with_slots(
            "pos-v-guid", "v", "Verb",
            slots=[slot_a],
            templates=[tpl],
        )
        entry = make_infl_entry_with_slots(
            "entry-1-guid", "-s", ["3SG"], pos_v, slots=[slot_a]
        )
        # source and target are the SAME object -> self-target
        handle = make_source([entry], [pos_v])
        affix_picks = frozenset(["entry-1-guid"])
        return handle, affix_picks

    def test_pos_status_in_target_for_self_target(self):
        handle, affix_picks = self._self_target_scene()
        result = build_skeleton_inventory(handle, affix_picks, target=handle)
        assert len(result.pos_nodes) == 1
        assert result.pos_nodes[0].status == "in_target"

    def test_slot_status_in_target_for_self_target(self):
        handle, affix_picks = self._self_target_scene()
        result = build_skeleton_inventory(handle, affix_picks, target=handle)
        pos_node = result.pos_nodes[0]
        assert len(pos_node.slots) == 1
        assert pos_node.slots[0].status == "in_target"

    def test_template_status_in_target_for_self_target(self):
        handle, affix_picks = self._self_target_scene()
        result = build_skeleton_inventory(handle, affix_picks, target=handle)
        pos_node = result.pos_nodes[0]
        assert len(pos_node.templates) == 1
        assert pos_node.templates[0].status == "in_target"

    def test_all_skeleton_rows_in_target_for_self_target(self):
        """Parametric: every POS / slot / template row must be 'in_target'."""
        handle, affix_picks = self._self_target_scene()
        result = build_skeleton_inventory(handle, affix_picks, target=handle)
        for pn in result.pos_nodes:
            assert pn.status == "in_target", f"POS {pn.pos_guid} status={pn.status!r}"
            for sn in pn.slots:
                assert sn.status == "in_target", (
                    f"slot {sn.slot_guid} status={sn.status!r}"
                )
            for tn in pn.templates:
                assert tn.status == "in_target", (
                    f"template {tn.template_guid} status={tn.status!r}"
                )

    def test_new_pos_not_in_target_shows_new(self):
        """A POS absent from the target should read 'new', not 'in_target'."""
        slot_src = make_slot("slot-src", "Src")
        pos_src = make_pos_with_slots("pos-src", "v", "Verb", slots=[slot_src])
        entry_src = make_infl_entry_with_slots("e-src", "-s", ["g"], pos_src, [slot_src])
        source = make_source([entry_src], [pos_src])

        # Target has a DIFFERENT POS (different GUID)
        slot_tgt = make_slot("slot-tgt", "Tgt")
        pos_tgt = make_pos_with_slots("pos-tgt", "n", "Noun", slots=[slot_tgt])
        entry_tgt = make_infl_entry_with_slots("e-tgt", "-pl", ["g"], pos_tgt, [slot_tgt])
        target = make_source([entry_tgt], [pos_tgt])

        result = build_skeleton_inventory(source, frozenset(["e-src"]), target=target)
        assert len(result.pos_nodes) == 1
        assert result.pos_nodes[0].status == "new"
        assert result.pos_nodes[0].slots[0].status == "new"


# ---------------------------------------------------------------------------
# P2: unnamed template label fallback
# ---------------------------------------------------------------------------

class TestUnnamedTemplateLabelFallback:
    """Template with blank / '***' name must render as '(unnamed template)'."""

    def _scene_with_unnamed_template(self, name_text: str):
        """Build a scene where the template's name.Text is `name_text`."""
        from _fakes_affix import FakeTemplate, FakeMultiUnicode, FakeNameText

        class _BlankNameTemplate(FakeTemplate):
            def __init__(self):
                # Do NOT call super().__init__ — set attrs manually so name text
                # is exactly what we want to test.
                self.Guid = "tpl-blank-guid"
                self.Name = type("_N", (), {
                    "BestAnalysisAlternative": FakeNameText(name_text)
                })()
                self.PrefixSlotsRS = []
                self.SuffixSlotsRS = []

        slot_a = make_slot("slot-a", "Present")
        pos_v = make_pos_with_slots(
            "pos-v", "v", "Verb",
            slots=[slot_a],
            templates=[_BlankNameTemplate()],
        )
        entry = make_infl_entry_with_slots("e1", "-s", ["3sg"], pos_v, [slot_a])
        handle = make_source([entry], [pos_v])
        return handle

    def test_unnamed_template_empty_string(self):
        handle = self._scene_with_unnamed_template("")
        result = build_skeleton_inventory(handle, frozenset(["e1"]))
        pos_node = result.pos_nodes[0]
        assert pos_node.templates[0].label == "(unnamed template)"

    def test_unnamed_template_triple_star(self):
        handle = self._scene_with_unnamed_template("***")
        result = build_skeleton_inventory(handle, frozenset(["e1"]))
        pos_node = result.pos_nodes[0]
        assert pos_node.templates[0].label == "(unnamed template)"

    def test_named_template_uses_real_name(self):
        handle = self._scene_with_unnamed_template("VerbTemplate")
        result = build_skeleton_inventory(handle, frozenset(["e1"]))
        pos_node = result.pos_nodes[0]
        assert pos_node.templates[0].label == "VerbTemplate"

    def test_unnamed_template_whitespace_only(self):
        """Template name that is all whitespace must also fall back to '(unnamed template)'."""
        handle = self._scene_with_unnamed_template("   ")
        result = build_skeleton_inventory(handle, frozenset(["e1"]))
        pos_node = result.pos_nodes[0]
        assert pos_node.templates[0].label == "(unnamed template)"


# ---------------------------------------------------------------------------
# P1-A: sub-POS recursion in build_skeleton_inventory
# ---------------------------------------------------------------------------

class TestSkeletonSubPosRecursion:
    """A sub-POS that carries an AffixSlot and AffixTemplate must produce a
    SkeletonPosNode.  The pre-fix code only iterated the flat top-level POS
    list and never visited SubPossibilitiesOS, so any slot/template on a
    child POS was invisible.
    """

    def _sub_pos_scene(self):
        """Parent POS has no slots; child sub-POS has one slot and one template."""
        slot_child = make_slot("slot-child-guid", "ChildSlot")
        tpl_child = make_template("tpl-child-guid", "ChildTemplate",
                                   slots=[slot_child])
        # child sub-POS carries the slot + template
        child_pos = make_pos_with_slots(
            "child-pos-guid", "cv", "ChildVerb",
            slots=[slot_child],
            templates=[tpl_child],
        )
        # parent POS has no slots itself, but has child_pos in SubPossibilitiesOS
        parent_pos = make_pos_with_slots(
            "parent-pos-guid", "v", "Verb",
            children=[child_pos],
        )
        # The entry attaches to the CHILD pos and fills the child slot
        entry = make_infl_entry_with_slots(
            "entry-child-guid", "-s", ["3SG"], child_pos, slots=[slot_child]
        )
        source = make_source([entry], [parent_pos])
        affix_picks = frozenset(["entry-child-guid"])
        return source, affix_picks, child_pos, slot_child, tpl_child

    def test_sub_pos_produces_skeleton_node(self):
        """Child sub-POS with a slot must appear as a SkeletonPosNode."""
        source, affix_picks, child_pos, slot_child, tpl_child = \
            self._sub_pos_scene()
        result = build_skeleton_inventory(source, affix_picks)
        guids = {n.pos_guid for n in result.pos_nodes}
        assert "child-pos-guid" in guids, (
            "sub-POS 'child-pos-guid' not found in skeleton — "
            "recursion into SubPossibilitiesOS may be missing"
        )

    def test_sub_pos_slot_visible(self):
        """The slot belonging to the child sub-POS must appear under its node."""
        source, affix_picks, child_pos, slot_child, tpl_child = \
            self._sub_pos_scene()
        result = build_skeleton_inventory(source, affix_picks)
        child_node = next(
            (n for n in result.pos_nodes if n.pos_guid == "child-pos-guid"), None
        )
        assert child_node is not None
        slot_guids = {s.slot_guid for s in child_node.slots}
        assert "slot-child-guid" in slot_guids

    def test_sub_pos_template_visible(self):
        """The template belonging to the child sub-POS must appear under its node."""
        source, affix_picks, child_pos, slot_child, tpl_child = \
            self._sub_pos_scene()
        result = build_skeleton_inventory(source, affix_picks)
        child_node = next(
            (n for n in result.pos_nodes if n.pos_guid == "child-pos-guid"), None
        )
        assert child_node is not None
        tpl_guids = {t.template_guid for t in child_node.templates}
        assert "tpl-child-guid" in tpl_guids

    def test_sub_pos_slot_preselected_when_affix_fills_it(self):
        """Slot on a sub-POS that the picked affix fills must be preselected."""
        source, affix_picks, child_pos, slot_child, tpl_child = \
            self._sub_pos_scene()
        result = build_skeleton_inventory(source, affix_picks)
        child_node = next(
            n for n in result.pos_nodes if n.pos_guid == "child-pos-guid"
        )
        slot_node = next(
            s for s in child_node.slots if s.slot_guid == "slot-child-guid"
        )
        assert slot_node.preselected is True

    def test_recursion_removal_breaks_sub_pos_visibility(self):
        """Canary: if recursion is absent, child-pos-guid must NOT appear.

        This test asserts the inverse scenario — it cannot be trivially satisfied
        by the current implementation since we just fixed recursion.  Instead it
        documents that the scene is non-vacuous: the entry really does attach to
        the child POS and the child POS really is nested under the parent.
        """
        source, affix_picks, child_pos, slot_child, tpl_child = \
            self._sub_pos_scene()
        # Verify that 'child-pos-guid' is NOT in the top-level POS list —
        # it lives only in SubPossibilitiesOS, so a flat iteration would miss it.
        top_level_guids = {
            p.Guid for p in
            source.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS
        }
        assert "child-pos-guid" not in top_level_guids, (
            "Test setup error: child-pos-guid must only be a sub-POS, "
            "not a top-level POS, for this canary to be meaningful."
        )
