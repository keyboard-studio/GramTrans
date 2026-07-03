"""Unit tests for spec 011 — Similar-Candidate Capture & Per-Item Resolution.

Covers:
  US1/SC-001/SC-002 — affix candidate capture (suggested_target_guid, dropdown)
  US2/SC-003/SC-004 — SimilarResolution three-way validation + inert Selection map
  US3/SC-005        — phonology matched_target_guid (collision-aware, lowest-HVO)
  Edge/D1/D2        — multi-candidate collision, HVO-ascending ordering
  D8 (lex-qc P1)    — _merge_row_glosses forwards suggested_target_guid
  FR-009/SC-006     — back-compat via defaulted fields
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.models import (
    GrammarCategory,
    Selection,
    SimilarCandidate,
    SimilarResolution,
)
from gramtrans.Lib.selection import (
    AffixRow,
    JunkDrawer,
    PosGroupedAffixInventory,
    build_pos_grouped_inventory,
    build_phonology_inventory,
)
from _fakes_affix import make_infl_entry, make_pos, make_source
from _fakes_phonology import FakeNC, FakePhonSource


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _with_hvo(entry, hvo: int):
    """Stamp an Hvo on a fake entry/object so HVO-ascending ordering is testable."""
    entry.Hvo = hvo
    return entry


def _all_infl_rows(inv):
    rows = []
    def _walk(node):
        rows.extend(node.inflectional)
        for c in node.children:
            _walk(c)
    for r in inv.roots:
        _walk(r)
    return rows


# ===========================================================================
# US2 / FR-007 / SC-003 — SimilarResolution three-way validation
# ===========================================================================

class TestSimilarResolutionValidation:
    def test_overwrite_without_target_raises(self):
        with pytest.raises(ValueError):
            SimilarResolution(entry_guid="g", action="overwrite")

    def test_merge_without_target_raises(self):
        with pytest.raises(ValueError):
            SimilarResolution(entry_guid="g", action="merge")

    def test_overwrite_with_target_ok(self):
        r = SimilarResolution(entry_guid="g", action="overwrite", target_guid="t")
        assert r.action == "overwrite" and r.target_guid == "t"

    def test_merge_with_target_ok(self):
        r = SimilarResolution(entry_guid="g", action="merge", target_guid="t")
        assert r.action == "merge" and r.target_guid == "t"

    def test_create_new_without_target_ok(self):
        r = SimilarResolution(entry_guid="g", action="create_new")
        assert r.action == "create_new" and r.target_guid is None

    def test_create_new_with_target_raises(self):
        with pytest.raises(ValueError):
            SimilarResolution(entry_guid="g", action="create_new", target_guid="t")

    def test_bogus_action_raises(self):
        with pytest.raises(ValueError):
            SimilarResolution(entry_guid="g", action="keep", target_guid="t")

    def test_frozen(self):
        r = SimilarResolution(entry_guid="g", action="create_new")
        with pytest.raises(Exception):
            r.action = "merge"  # type: ignore[misc]


# ===========================================================================
# US2 / FR-008 / SC-004 — Selection.similar_resolutions inert-when-off
# ===========================================================================

class TestSelectionSimilarResolutions:
    def test_default_empty(self):
        assert Selection().similar_resolutions == {}

    def test_resolution_for_absent_returns_none(self):
        assert Selection().similar_resolution_for("nope") is None

    def test_resolution_for_present(self):
        r = SimilarResolution(entry_guid="g", action="overwrite", target_guid="t")
        sel = Selection(similar_resolutions={"g": r})
        assert sel.similar_resolution_for("g") is r

    def test_no_post_init_guard_for_off_category(self):
        """A resolution for an entry with no category enabled must NOT raise
        (follows leaf_item_picks inert precedent, NOT the guarded affix_picks)."""
        r = SimilarResolution(entry_guid="x", action="merge", target_guid="t")
        # categories empty -> no AFFIXES etc.; must construct fine.
        sel = Selection(similar_resolutions={"x": r})
        assert sel.similar_resolution_for("x") is r

    def test_inert_other_fields_unchanged(self):
        """Populating similar_resolutions leaves all other public accessors equal."""
        base = Selection(categories={GrammarCategory.PHONEMES: True})
        r = SimilarResolution(entry_guid="g", action="create_new")
        withmap = Selection(
            categories={GrammarCategory.PHONEMES: True},
            similar_resolutions={"g": r},
        )
        assert base.is_on(GrammarCategory.PHONEMES) == withmap.is_on(GrammarCategory.PHONEMES)
        assert base.scope_for(GrammarCategory.PHONEMES) == withmap.scope_for(GrammarCategory.PHONEMES)
        assert base.leaf_picks_for(GrammarCategory.PHONEMES) == withmap.leaf_picks_for(GrammarCategory.PHONEMES)


# ===========================================================================
# US1 / FR-001..FR-005 / SC-001 / SC-002 — affix candidate capture
# ===========================================================================

class TestAffixCandidateCapture:
    def test_similar_row_has_suggested_match(self):
        pos = make_pos("pv", "v")
        src = make_source([make_infl_entry("src-1", "foo", ["gl"], pos)], [pos])
        # target: different guid, same form -> SIMILAR
        tgt = make_source(
            [_with_hvo(make_infl_entry("tgt-1", "foo", ["tg"], pos), 10)], [pos])
        inv = build_pos_grouped_inventory(src, target=tgt)
        row = _all_infl_rows(inv)[0]
        assert row.status == "similar"
        assert row.suggested_target_guid == "tgt-1"

    def test_new_row_suggested_is_none(self):
        pos = make_pos("pv", "v")
        src = make_source([make_infl_entry("src-1", "unique", ["gl"], pos)], [pos])
        tgt = make_source([make_infl_entry("tgt-1", "different", ["tg"], pos)], [pos])
        inv = build_pos_grouped_inventory(src, target=tgt)
        row = _all_infl_rows(inv)[0]
        assert row.status == "new"
        assert row.suggested_target_guid is None

    def test_no_target_suggested_none_and_empty_dropdown(self):
        pos = make_pos("pv", "v")
        src = make_source([make_infl_entry("src-1", "foo", ["gl"], pos)], [pos])
        inv = build_pos_grouped_inventory(src)  # no target
        row = _all_infl_rows(inv)[0]
        assert row.suggested_target_guid is None
        assert inv.target_affix_candidates == ()

    def test_multi_candidate_ordered_by_hvo_lowest_first(self):
        """Live-proven case (form 'n' -> multiple target affixes): the suggested
        match is the LOWEST-HVO candidate, not the alphabetically-first GUID."""
        pos = make_pos("pv", "v")
        src = make_source([make_infl_entry("src-n", "n", ["1sg"], pos)], [pos])
        # Two target affixes share form 'n'; give the alphabetically-LATER guid
        # the LOWER hvo so we prove HVO (not guid) drives the pick.
        t_hi = _with_hvo(make_infl_entry("aaa-late", "n", ["3sg.n"], pos), 99)
        t_lo = _with_hvo(make_infl_entry("zzz-early", "n", ["1.n"], pos), 1)
        tgt = make_source([t_hi, t_lo], [pos])
        inv = build_pos_grouped_inventory(src, target=tgt)
        row = _all_infl_rows(inv)[0]
        assert row.status == "similar"
        assert row.suggested_target_guid == "zzz-early"  # lowest HVO wins

    def test_dropdown_dedup_covers_all_candidates(self):
        pos = make_pos("pv", "v")
        src = make_source([
            make_infl_entry("s1", "n", ["x"], pos),
            make_infl_entry("s2", "a", ["y"], pos),
        ], [pos])
        tgt = make_source([
            _with_hvo(make_infl_entry("t-n1", "n", ["g1"], pos), 1),
            _with_hvo(make_infl_entry("t-n2", "n", ["g2"], pos), 2),
            _with_hvo(make_infl_entry("t-a1", "a", ["g3"], pos), 3),
        ], [pos])
        inv = build_pos_grouped_inventory(src, target=tgt)
        cands = inv.target_affix_candidates
        guids = [c.target_guid for c in cands]
        # deduped: each target guid exactly once (SC-002)
        assert len(guids) == len(set(guids)) == 3
        assert set(guids) == {"t-n1", "t-n2", "t-a1"}
        # HVO-ascending order
        assert guids == ["t-n1", "t-n2", "t-a1"]
        # SimilarCandidate carries form + gloss
        by_guid = {c.target_guid: c for c in cands}
        assert by_guid["t-n1"].form == "n"
        assert by_guid["t-a1"].gloss == "g3"

    def test_similarcandidate_captures_triple(self):
        c = SimilarCandidate(target_guid="tg", form="n~", gloss="1sg.PFV")
        assert (c.target_guid, c.form, c.gloss) == ("tg", "n~", "1sg.PFV")


# ===========================================================================
# D8 / lex-qc P1 — _merge_row_glosses forwards suggested_target_guid
# ===========================================================================

class TestGlossMergeForwardsSuggestion:
    def test_similar_row_keeps_suggestion_after_gloss_merge(self):
        pos = make_pos("pv", "v")
        # Source affix with TWO inflectional MSAs on the SAME pos/role -> the
        # second collapses via _merge_row_glosses into the first row.
        from _fakes_affix import FakeEntry, FakeInflMsa, FakeSense
        msa1 = FakeInflMsa(pos)
        msa2 = FakeInflMsa(pos)
        e = FakeEntry("src-merge", "foo", True,
                      senses=[FakeSense("glossA", msa1), FakeSense("glossB", msa2)],
                      msas=[msa1, msa2])
        src = make_source([e], [pos])
        tgt = make_source(
            [_with_hvo(make_infl_entry("tgt-foo", "foo", ["tg"], pos), 5)], [pos])
        inv = build_pos_grouped_inventory(src, target=tgt)
        rows = _all_infl_rows(inv)
        assert len(rows) == 1  # the two MSAs collapsed to one row
        row = rows[0]
        assert row.status == "similar"
        # Regression: suggestion survives the gloss-merge (not reset to None).
        assert row.suggested_target_guid == "tgt-foo"


# ===========================================================================
# US3 / FR-006 / SC-005 — phonology matched_target_guid
# ===========================================================================

class TestPhonologyMatchedTargetGuid:
    def _nc_group(self, inv):
        return inv.group_for(GrammarCategory.NATURAL_CLASSES)

    def test_similar_nc_carries_matched_guid(self):
        src = FakePhonSource(ncs=[FakeNC("src-nc", "Consonants")])
        tgt = FakePhonSource(ncs=[FakeNC("tgt-nc", "Consonants")])
        inv = build_phonology_inventory(src, target=tgt)
        row = self._nc_group(inv).rows[0]
        assert row.status == "similar"
        assert row.matched_target_guid == "tgt-nc"

    def test_new_nc_matched_guid_none(self):
        src = FakePhonSource(ncs=[FakeNC("src-nc", "Vowels")])
        tgt = FakePhonSource(ncs=[FakeNC("tgt-nc", "Consonants")])
        inv = build_phonology_inventory(src, target=tgt)
        row = self._nc_group(inv).rows[0]
        assert row.status == "new"
        assert row.matched_target_guid is None

    def test_no_target_matched_guid_none(self):
        src = FakePhonSource(ncs=[FakeNC("src-nc", "Consonants")])
        inv = build_phonology_inventory(src)  # no target
        row = self._nc_group(inv).rows[0]
        assert row.status is None
        assert row.matched_target_guid is None

    def test_label_collision_picks_lowest_hvo(self):
        """Live-proven: all Ejagham NaturalClass names collide. The matched GUID
        is the lowest-HVO target object, deterministically."""
        src = FakePhonSource(ncs=[FakeNC("src-nc", "Consonants")])
        t_hi = _with_hvo(FakeNC("aaa-late", "Consonants"), 99)
        t_lo = _with_hvo(FakeNC("zzz-early", "Consonants"), 1)
        tgt = FakePhonSource(ncs=[t_hi, t_lo])
        inv = build_phonology_inventory(src, target=tgt)
        row = self._nc_group(inv).rows[0]
        assert row.status == "similar"
        assert row.matched_target_guid == "zzz-early"  # lowest HVO wins


# ===========================================================================
# FR-009 / SC-006 — back-compat via defaulted fields
# ===========================================================================

class TestBackCompat:
    def test_affixrow_constructs_without_new_field(self):
        r = AffixRow(entry_guid="g", form="f", glosses="gl", msa_kind="infl",
                     from_pos=None, to_pos=None, role="attaches")
        assert r.suggested_target_guid is None

    def test_inventory_constructs_without_candidates(self):
        inv = PosGroupedAffixInventory(roots=(), junk=JunkDrawer((), ()))
        assert inv.target_affix_candidates == ()

    def test_selection_constructs_without_similar_resolutions(self):
        assert Selection().similar_resolutions == {}
