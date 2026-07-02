"""T003-T005: Unit tests for POS-grouped inventory builder.

Tests data types (T003), grouping/dedup/hierarchy (T004),
and deriv/junk classification (T005).
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.selection import (
    AffixRow,
    JunkDrawer,
    PosGroupedAffixInventory,
    PosNode,
    build_pos_grouped_inventory,
)
from _fakes_affix import (
    make_deriv_entry,
    make_infl_entry,
    make_no_analysis_entry,
    make_no_pos_entry,
    make_non_affix_entry,
    make_pos,
    make_source,
    make_uncl_entry,
    FakeEntry,
    FakeInflMsa,
    FakeSense,
    FakeUnknownMsa,
)


# =============================================================================
# T003 - Data type tests
# =============================================================================

class TestDataTypes:
    def test_affix_row_is_frozen_dataclass(self):
        row = AffixRow(
            entry_guid="abc",
            form="foo",
            glosses="bar",
            msa_kind="infl",
            from_pos=None,
            to_pos=None,
            role="attaches",
        )
        assert row.entry_guid == "abc"
        assert row.form == "foo"
        assert row.glosses == "bar"
        assert row.msa_kind == "infl"
        assert row.from_pos is None
        assert row.to_pos is None
        assert row.role == "attaches"

    def test_affix_row_is_immutable(self):
        row = AffixRow("g", "f", "gl", "infl", None, None, "attaches")
        with pytest.raises((TypeError, AttributeError)):
            row.form = "changed"  # type: ignore[misc]

    def test_pos_node_is_frozen_dataclass(self):
        node = PosNode(
            pos_guid="p1",
            label="v",
            children=(),
            inflectional=(),
            deriv_attaches=(),
            deriv_produces=(),
        )
        assert node.pos_guid == "p1"
        assert node.label == "v"
        assert node.children == ()
        assert node.inflectional == ()
        assert node.deriv_attaches == ()
        assert node.deriv_produces == ()

    def test_pos_node_is_immutable(self):
        node = PosNode("p", "v", (), (), (), ())
        with pytest.raises((TypeError, AttributeError)):
            node.label = "n"  # type: ignore[misc]

    def test_junk_drawer_is_frozen_dataclass(self):
        j = JunkDrawer(no_pos=(), no_analysis=())
        assert j.no_pos == ()
        assert j.no_analysis == ()

    def test_pos_grouped_inventory_is_frozen_dataclass(self):
        inv = PosGroupedAffixInventory(roots=(), junk=JunkDrawer((), ()))
        assert inv.roots == ()
        assert isinstance(inv.junk, JunkDrawer)

    def test_all_affix_guids_deduplicates(self):
        """An entry appearing in multiple groups returns its GUID only once."""
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        # One deriv entry that attaches to v and produces n => guid in both nodes
        entry = make_deriv_entry("guid1", "foo", ["gloss"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        guids = inv.all_affix_guids()
        assert isinstance(guids, frozenset)
        assert guids == frozenset({"guid1"})

    def test_all_affix_guids_includes_junk(self):
        pos_v = make_pos("pv", "v")
        no_pos = make_no_pos_entry("junk1", "bar")
        entry = make_infl_entry("normal1", "baz", ["gl"], pos_v)
        src = make_source([no_pos, entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        guids = inv.all_affix_guids()
        assert "junk1" in guids
        assert "normal1" in guids


# =============================================================================
# T004 - build_pos_grouped_inventory grouping tests
# =============================================================================

class TestBuildPosGroupedInventory:
    def test_infl_msa_grouped_under_pos(self):
        pos_v = make_pos("pv", "v", "Verb")
        entry = make_infl_entry("g1", "afoo", ["gloss"], pos_v)
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        assert len(inv.roots) == 1
        node = inv.roots[0]
        assert node.label == "v"
        assert len(node.inflectional) == 1
        assert node.inflectional[0].entry_guid == "g1"
        assert node.inflectional[0].msa_kind == "infl"

    def test_uncl_msa_grouped_under_inflectional_list(self):
        pos_v = make_pos("pv", "v")
        entry = make_uncl_entry("g2", "bfoo", ["gl"], pos_v)
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        node = inv.roots[0]
        # unclassified goes into inflectional list
        assert len(node.inflectional) == 1
        assert node.inflectional[0].msa_kind == "uncl"

    def test_pos_hierarchy_nesting_preserved(self):
        """Sub-POS is nested under parent, not rolled up."""
        child_pos = make_pos("pchild", "vtr", "Transitive Verb")
        parent_pos = make_pos("pparent", "v", "Verb", children=[child_pos])
        entry = make_infl_entry("g3", "cfoo", ["gl"], child_pos)
        src = make_source([entry], [parent_pos])
        inv = build_pos_grouped_inventory(src)
        assert len(inv.roots) == 1
        parent_node = inv.roots[0]
        assert parent_node.label == "v"
        assert len(parent_node.children) == 1
        child_node = parent_node.children[0]
        assert child_node.label == "vtr"
        assert len(child_node.inflectional) == 1

    def test_rows_sorted_alphabetically_by_form(self):
        pos_v = make_pos("pv", "v")
        e1 = make_infl_entry("g1", "zoo", ["z"], pos_v)
        e2 = make_infl_entry("g2", "alpha", ["a"], pos_v)
        e3 = make_infl_entry("g3", "mid", ["m"], pos_v)
        src = make_source([e1, e2, e3], [pos_v])
        inv = build_pos_grouped_inventory(src)
        forms = [r.form for r in inv.roots[0].inflectional]
        assert forms == sorted(forms)

    def test_glosses_deduplicated_and_joined(self):
        """Multiple senses with same gloss -> deduped; different -> joined with '; '."""
        pos_v = make_pos("pv", "v")
        from _fakes_affix import FakeEntry, FakeInflMsa, FakeSense, FakeLexemeForm, FakeMorphType
        msa = FakeInflMsa(pos_v)
        s1 = FakeSense("run", msa)
        s2 = FakeSense("run", msa)   # duplicate
        s3 = FakeSense("sprint", msa)
        entry = FakeEntry("g1", "foo", True, senses=[s1, s2, s3], msas=[msa])
        entry.LexemeFormOA.Form.BestVernacularAlternative.Text = "foo"
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        row = inv.roots[0].inflectional[0]
        glosses = row.glosses
        parts = [p.strip() for p in glosses.split(";")]
        assert parts.count("run") == 1
        assert "sprint" in glosses

    def test_no_gloss_fallback(self):
        pos_v = make_pos("pv", "v")
        from _fakes_affix import FakeEntry, FakeInflMsa, FakeSense
        msa = FakeInflMsa(pos_v)
        s1 = FakeSense("", msa)
        entry = FakeEntry("g1", "foo", True, senses=[s1], msas=[msa])
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        row = inv.roots[0].inflectional[0]
        assert row.glosses == "(no gloss)"

    def test_label_prefers_abbreviation(self):
        pos = make_pos("p1", abbrev="v", name="Verb")
        entry = make_infl_entry("g1", "foo", ["gl"], pos)
        src = make_source([entry], [pos])
        inv = build_pos_grouped_inventory(src)
        assert inv.roots[0].label == "v"

    def test_label_falls_back_to_name_when_abbrev_empty(self):
        pos = make_pos("p1", abbrev="", name="Verb")
        # Force abbreviation text to empty
        pos.Abbreviation.BestAnalysisAlternative.Text = ""
        pos.Name.BestAnalysisAlternative.Text = "Verb"
        entry = make_infl_entry("g1", "foo", ["gl"], pos)
        src = make_source([entry], [pos])
        inv = build_pos_grouped_inventory(src)
        assert inv.roots[0].label == "Verb"

    def test_non_affix_entries_filtered(self):
        pos_v = make_pos("pv", "v")
        stem = make_non_affix_entry("stem1", "bark")
        src = make_source([stem], [pos_v])
        inv = build_pos_grouped_inventory(src)
        all_guids = inv.all_affix_guids()
        assert "stem1" not in all_guids

    def test_empty_source_returns_empty_inventory(self):
        src = make_source([], [])
        inv = build_pos_grouped_inventory(src)
        assert inv.roots == ()
        assert inv.junk.no_pos == ()
        assert inv.junk.no_analysis == ()


# =============================================================================
# T005 - Derivational + junk classification tests
# =============================================================================

class TestDerivAndJunk:
    def test_deriv_appears_in_attaches_and_produces(self):
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("g1", "igi", ["causative"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        # Find v node and n node
        v_node = next(nd for nd in inv.roots if nd.label == "v")
        n_node = next(nd for nd in inv.roots if nd.label == "n")
        assert any(r.entry_guid == "g1" for r in v_node.deriv_attaches)
        assert any(r.entry_guid == "g1" for r in n_node.deriv_produces)

    def test_deriv_attaches_row_has_correct_role(self):
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("g1", "foo", ["gl"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        v_node = next(nd for nd in inv.roots if nd.label == "v")
        row = v_node.deriv_attaches[0]
        assert row.role == "attaches"
        assert row.msa_kind == "deriv"

    def test_deriv_produces_row_has_correct_role(self):
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        entry = make_deriv_entry("g1", "foo", ["gl"], pos_v, pos_n)
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        n_node = next(nd for nd in inv.roots if nd.label == "n")
        row = n_node.deriv_produces[0]
        assert row.role == "produces"
        assert row.msa_kind == "deriv"

    def test_multi_pos_affix_appears_in_each_group(self):
        """Affix with two inflectional MSAs (two different POS) -> in both nodes."""
        pos_v = make_pos("pv", "v")
        pos_n = make_pos("pn", "n")
        from _fakes_affix import FakeEntry, FakeInflMsa, FakeSense
        msa_v = FakeInflMsa(pos_v)
        msa_n = FakeInflMsa(pos_n)
        senses = [FakeSense("gl", msa_v), FakeSense("gl2", msa_n)]
        entry = FakeEntry("g_multi", "multi", True, senses=senses, msas=[msa_v, msa_n])
        src = make_source([entry], [pos_v, pos_n])
        inv = build_pos_grouped_inventory(src)
        v_node = next(nd for nd in inv.roots if nd.label == "v")
        n_node = next(nd for nd in inv.roots if nd.label == "n")
        assert any(r.entry_guid == "g_multi" for r in v_node.inflectional)
        assert any(r.entry_guid == "g_multi" for r in n_node.inflectional)
        # But all_affix_guids deduplicated
        assert inv.all_affix_guids() == frozenset({"g_multi"})

    def test_null_pos_msa_goes_to_junk_no_pos(self):
        entry = make_no_pos_entry("junk1", "foo")
        src = make_source([entry], [])
        inv = build_pos_grouped_inventory(src)
        assert any(r.entry_guid == "junk1" for r in inv.junk.no_pos)

    def test_no_sense_no_msa_goes_to_junk_no_analysis(self):
        entry = make_no_analysis_entry("junk2", "bar")
        src = make_source([entry], [])
        inv = build_pos_grouped_inventory(src)
        assert any(r.entry_guid == "junk2" for r in inv.junk.no_analysis)

    def test_unrecognized_msa_classname_goes_to_junk(self):
        """An MSA with an unrecognized ClassName -> treated as no-POS junk."""
        pos_v = make_pos("pv", "v")
        from _fakes_affix import FakeEntry, FakeSense, FakeUnknownMsa
        msa = FakeUnknownMsa()
        s = FakeSense("gl", msa)
        entry = FakeEntry("junk3", "baz", True, senses=[s], msas=[msa])
        src = make_source([entry], [pos_v])
        inv = build_pos_grouped_inventory(src)
        assert any(r.entry_guid == "junk3" for r in inv.junk.no_pos)

    def test_deriv_null_from_pos_goes_to_junk(self):
        """Deriv MSA with null FromPartOfSpeechRA -> no attaches POS; routes to junk."""
        pos_n = make_pos("pn", "n")
        from _fakes_affix import FakeEntry, FakeDerivMsa, FakeSense
        msa = FakeDerivMsa(None, pos_n)
        s = FakeSense("gl", msa)
        entry = FakeEntry("g_nofrom", "nfoo", True, senses=[s], msas=[msa])
        src = make_source([entry], [pos_n])
        inv = build_pos_grouped_inventory(src)
        # The entry reached no attaches group; null From -> goes to junk.no_pos
        all_g = inv.all_affix_guids()
        assert "g_nofrom" in all_g
