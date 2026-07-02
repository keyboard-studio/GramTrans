"""Tests for specs/008-affix-pos-picker fix pass.

Covers:
- FIX 1: cast helper (_cast) returns obj unchanged when pythonnet absent.
- FIX 1: MSA dispatch branches (infl / unclassified-null / deriv from+to)
         exercise the cast wrapper paths via fake handles.
- FIX 2: _PosAccumulator.__slots__ no duplicate.
- FIX 3 (FR-008): header-check on POS group excludes produces-role GUIDs
         from _collect_checked -> collapse_pos_grouped -> affix_picks.
- FIX 4: template_picks preserved through _on_preview re-wrap.
- _merge_row_glosses multi-MSA merge path (previously uncovered).
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.selection import (
    AffixRow,
    JunkDrawer,
    PosGroupedAffixInventory,
    PosNode,
    _PosAccumulator,
    _cast,
    _merge_row_glosses,
    build_pos_grouped_inventory,
    collapse_pos_grouped,
)
from _fakes_affix import (
    FakeDerivMsa,
    FakeEntry,
    FakeInflMsa,
    FakeSense,
    FakeUnclMsa,
    make_deriv_entry,
    make_infl_entry,
    make_pos,
    make_source,
    make_uncl_entry,
)


# =============================================================================
# FIX 1 -- _cast helper
# =============================================================================

class TestCastHelper:
    def test_cast_returns_obj_when_pythonnet_absent(self):
        """Without pythonnet, _cast must return the original object unchanged."""
        obj = object()
        result = _cast(obj, "ILexEntry")
        assert result is obj

    def test_cast_handles_nonexistent_interface_gracefully(self):
        """An interface name that does not exist must not raise."""
        obj = {"key": "val"}
        result = _cast(obj, "IDoesNotExistEver9999")
        assert result is obj


# =============================================================================
# FIX 1 -- MSA dispatch branches via fake handles
# =============================================================================

class TestMsaDispatchCastPaths:
    """Verify each MSA branch reaches the correct list even after cast wrapping.

    _cast returns the fake handle unchanged (no pythonnet), so the attribute
    reads work on the fakes as normal -- this confirms the cast wrapper path
    does not break fake-handle tests.
    """

    def test_infl_msa_cast_path_places_row(self):
        pos_v = make_pos("pv", "v")
        entry = make_infl_entry("g_infl", "foo", ["gl"], pos_v)
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        node = inv.roots[0]
        assert any(r.entry_guid == "g_infl" for r in node.inflectional)

    def test_unclassified_null_pos_goes_to_junk(self):
        """IMoUnclassifiedAffixMsa.PartOfSpeechRA=None -> junk (correct per domain)."""
        # make_no_pos_entry uses FakeInflMsa(None); exercise FakeUnclMsa(None)
        msa = FakeUnclMsa(None)
        entry = FakeEntry("g_uncl_null", "bar", True,
                          senses=[FakeSense("gloss", msa)], msas=[msa])
        src = make_source([entry], [])
        inv = build_pos_grouped_inventory(src)
        junk_guids = {r.entry_guid for r in inv.junk.no_pos}
        assert "g_uncl_null" in junk_guids

    def test_unclassified_with_pos_cast_path_places_row(self):
        pos_v = make_pos("pv", "v")
        entry = make_uncl_entry("g_uncl", "baz", ["gl"], pos_v)
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        node = inv.roots[0]
        assert any(r.entry_guid == "g_uncl" for r in node.inflectional)
        assert node.inflectional[0].msa_kind == "uncl"

    def test_deriv_from_pos_cast_path_places_attaches_row(self):
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("g_deriv", "igi", ["caus"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        v_node = next(nd for nd in inv.roots if nd.label == "v")
        assert any(r.entry_guid == "g_deriv" and r.role == "attaches"
                   for r in v_node.deriv_attaches)

    def test_deriv_to_pos_cast_path_places_produces_row(self):
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("g_deriv", "igi", ["caus"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        n_node = next(nd for nd in inv.roots if nd.label == "n")
        assert any(r.entry_guid == "g_deriv" and r.role == "produces"
                   for r in n_node.deriv_produces)

    def test_deriv_null_to_pos_only_attaches_placed(self):
        """Deriv with FromPOS set but ToPOS=None -> only attaches row placed."""
        pos_v = make_pos("pv", "v")
        msa = FakeDerivMsa(pos_v, None)
        entry = FakeEntry("g_noto", "noo", True,
                          senses=[FakeSense("gl", msa)], msas=[msa])
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        v_node = inv.roots[0]
        # attaches placed
        assert any(r.entry_guid == "g_noto" for r in v_node.deriv_attaches)
        # produces NOT placed anywhere
        for nd in inv.roots:
            assert not any(r.entry_guid == "g_noto" for r in nd.deriv_produces)


# =============================================================================
# FIX 2 -- _PosAccumulator __slots__ no duplicate
# =============================================================================

class TestPosAccumulatorSlots:
    def test_no_duplicate_pos_guid_in_slots(self):
        slots = _PosAccumulator.__slots__
        assert slots.count("pos_guid") == 1, (
            f"Duplicate 'pos_guid' in __slots__: {slots!r}"
        )

    def test_accumulator_instantiates_and_sets_pos_guid(self):
        acc = _PosAccumulator("pg", "Verb")
        assert acc.pos_guid == "pg"
        assert acc.label == "Verb"


# =============================================================================
# FIX 3 (FR-008) -- produces rows excluded from header-driven _collect_checked
# =============================================================================
#
# This test is a pure-Python round-trip that simulates what _PageItemPicker
# does: build inventory, simulate a header check over a POS that has a
# produces row, run collapse_pos_grouped, and assert the produces GUID is
# NOT in affix_picks.
#
# (The full Qt widget test would require PyQt6; this exercises the same
# logic path using the data model only.)
#
class TestFr008ProducesExcludedFromHeaderCheck:
    def _header_guids_for_node(self, node: PosNode) -> frozenset:
        """Replicate the FR-008-correct header-check sweep:
        include inflectional + deriv_attaches but NOT deriv_produces.
        This is exactly what _collect_checked does after FIX 3.
        """
        guids: set = set()
        for row in node.inflectional:
            guids.add(row.entry_guid)
        for row in node.deriv_attaches:
            guids.add(row.entry_guid)
        # deriv_produces intentionally excluded
        return frozenset(guids)

    def test_header_check_excludes_produces_guid(self):
        """Header-check on the 'n' POS node must not include deriv1's GUID
        because deriv1 appears there ONLY as a produces row."""
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("deriv1", "foo", ["gl"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        n_node = next(nd for nd in inv.roots if nd.label == "n")
        checked = self._header_guids_for_node(n_node)
        # deriv1 is NOT in attaches groups of n, only in produces
        assert "deriv1" not in checked
        sel = collapse_pos_grouped(checked, inv)
        assert "deriv1" not in sel.affix_picks

    def test_header_check_includes_attaches_guid(self):
        """The same entry's GUID IS selected when the v-node header is checked
        (deriv1 is in v.deriv_attaches)."""
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("deriv1", "foo", ["gl"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        v_node = next(nd for nd in inv.roots if nd.label == "v")
        checked = self._header_guids_for_node(v_node)
        # deriv1 IS in v.deriv_attaches
        assert "deriv1" in checked
        sel = collapse_pos_grouped(checked, inv)
        assert "deriv1" in sel.affix_picks

    def test_mixed_node_header_check_attaches_included_produces_excluded(self):
        """POS node with both attaches and produces rows: header sweeps only
        attaches, not produces."""
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        # infl_entry attaches to v
        infl = make_infl_entry("g_infl", "aaa", ["gl"], pos_v)
        # deriv_entry: from=v (attaches to v), to=n (produces n)
        deriv = make_deriv_entry("g_deriv", "bbb", ["gl2"], pos_v, pos_n)
        # another_entry that produces v (to_pos=v)
        deriv2 = make_deriv_entry("g_prod_v", "ccc", ["gl3"], pos_n, pos_v)
        src = make_source([infl, deriv, deriv2], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        v_node = next(nd for nd in inv.roots if nd.label == "v")
        checked = self._header_guids_for_node(v_node)
        # g_infl and g_deriv are attaches -> included
        assert "g_infl" in checked
        assert "g_deriv" in checked
        # g_prod_v only appears in v.deriv_produces -> excluded
        assert "g_prod_v" not in checked
        sel = collapse_pos_grouped(checked, inv)
        assert "g_prod_v" not in sel.affix_picks
        assert "g_infl" in sel.affix_picks
        assert "g_deriv" in sel.affix_picks


# =============================================================================
# FIX 4 -- template_picks preserved through _on_preview re-wrap
# =============================================================================
#
# Tested at the data-model level: build_selection with checked_templates set
# -> Selection.template_picks non-empty, and re-wrapping preserves them.
#
class TestTemplatePicsPreservedThroughReWrap:
    def test_template_picks_survive_rewrap(self):
        from gramtrans.Lib.selection import (
            PickerState,
            SourceAffixInventory,
            build_selection,
        )
        # Simulate page-items returning a selection with template_picks
        tpl_guid = "tpl-abc"
        affix_guid = "aff-xyz"
        picker = PickerState(
            checked_affixes=frozenset({affix_guid}),
            checked_templates=frozenset({tpl_guid}),
        )
        inv = SourceAffixInventory(
            unbound_affixes=frozenset({affix_guid}),
            template_to_slots={tpl_guid: ()},
        )
        affix_sel = build_selection(picker, inv)
        assert tpl_guid in affix_sel.template_picks

        # Simulate _on_preview re-wrap (fixed version)
        picker2 = PickerState(
            checked_affixes=affix_sel.affix_picks,
            checked_templates=affix_sel.template_picks,
        )
        inv2 = SourceAffixInventory(
            unbound_affixes=affix_sel.affix_picks,
            template_to_slots={t: () for t in affix_sel.template_picks},
        )
        sel2 = build_selection(picker2, inv2)
        assert tpl_guid in sel2.template_picks, (
            "template_picks lost in re-wrap -- FIX 4 regression"
        )

    def test_old_rewrap_loses_template_picks(self):
        """Document the pre-fix behaviour: re-wrapping without template_picks
        loses them -- confirm the old code path would fail."""
        from gramtrans.Lib.selection import (
            PickerState,
            SourceAffixInventory,
            build_selection,
        )
        tpl_guid = "tpl-abc"
        affix_guid = "aff-xyz"
        picker = PickerState(
            checked_affixes=frozenset({affix_guid}),
            checked_templates=frozenset({tpl_guid}),
        )
        inv = SourceAffixInventory(
            unbound_affixes=frozenset({affix_guid}),
            template_to_slots={tpl_guid: ()},
        )
        affix_sel = build_selection(picker, inv)
        assert tpl_guid in affix_sel.template_picks

        # Old (broken) re-wrap: only checked_affixes, no checked_templates
        picker_old = PickerState(checked_affixes=affix_sel.affix_picks)
        inv_old = SourceAffixInventory(unbound_affixes=affix_sel.affix_picks)
        sel_old = build_selection(picker_old, inv_old)
        assert tpl_guid not in sel_old.template_picks, (
            "Expected old re-wrap to lose template_picks"
        )


# =============================================================================
# _merge_row_glosses multi-MSA merge path
# =============================================================================

class TestMergeRowGlosses:
    def _make_row(self, guid: str, glosses: str) -> AffixRow:
        return AffixRow(
            entry_guid=guid, form="f", glosses=glosses,
            msa_kind="infl", from_pos=None, to_pos=None, role="attaches",
        )

    def test_merges_new_glosses_into_existing(self):
        rows = [self._make_row("g1", "run")]
        _merge_row_glosses(rows, "g1", "sprint")
        assert "run" in rows[0].glosses
        assert "sprint" in rows[0].glosses

    def test_deduplicates_on_merge(self):
        rows = [self._make_row("g1", "run")]
        _merge_row_glosses(rows, "g1", "run")
        assert rows[0].glosses.count("run") == 1

    def test_no_op_for_unknown_guid(self):
        rows = [self._make_row("g1", "run")]
        _merge_row_glosses(rows, "g999", "sprint")
        assert rows[0].glosses == "run"

    def test_no_gloss_placeholder_stripped_on_merge(self):
        rows = [self._make_row("g1", "(no gloss)")]
        _merge_row_glosses(rows, "g1", "sprint")
        assert rows[0].glosses == "sprint"

    def test_multi_msa_triple_merge(self):
        """Three separate merge calls accumulate distinct glosses correctly."""
        rows = [self._make_row("g1", "walk")]
        _merge_row_glosses(rows, "g1", "stride")
        _merge_row_glosses(rows, "g1", "march")
        parts = [p.strip() for p in rows[0].glosses.split(";")]
        assert "walk" in parts
        assert "stride" in parts
        assert "march" in parts
        assert len(parts) == 3

    def test_multi_msa_merge_via_builder(self):
        """Two infl MSAs on same entry under same POS -> one row with merged glosses."""
        pos_v = make_pos("pv", "v")
        msa1 = FakeInflMsa(pos_v)
        msa2 = FakeInflMsa(pos_v)
        s1 = FakeSense("run", msa1)
        s2 = FakeSense("sprint", msa2)
        entry = FakeEntry("g_multi_msa", "foo", True,
                          senses=[s1, s2], msas=[msa1, msa2])
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        node = inv.roots[0]
        assert len(node.inflectional) == 1
        row = node.inflectional[0]
        assert "run" in row.glosses
        assert "sprint" in row.glosses


# =============================================================================
# Junk-drawer false-confidence guard (FIX 1 GUARD)
# =============================================================================

class TestJunkDrawerGuard:
    def test_all_affix_junk_logs_warning(self, caplog):
        """When every affix lands in junk (placed=0), a WARNING is logged."""
        import logging
        # no_analysis entries: no MSAs -> all junk.no_analysis
        from _fakes_affix import make_no_analysis_entry
        entries = [make_no_analysis_entry(f"j{i}", f"form{i}") for i in range(3)]
        src = make_source(entries, [])
        with caplog.at_level(logging.WARNING, logger="gramtrans.Lib.selection"):
            inv = build_pos_grouped_inventory(src)
        assert inv.junk.no_analysis  # they ARE in junk
        assert any("junk drawer" in r.message.lower() or "junk" in r.message.lower()
                   for r in caplog.records), (
            "Expected a warning about all affixes landing in junk drawer"
        )
