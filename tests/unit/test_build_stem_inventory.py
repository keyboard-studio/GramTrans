"""019 stem item picker — inventory, MSA dispatch, closure, target status,
and missing-reference aggregation.

Covers tasks T006, T011, T011a, T012, T013, T019, T021. Uses the fake
infrastructure in ``_fakes_affix`` / ``_fakes_stem`` — no pyflexicon / FLEx.
"""
from __future__ import annotations

from _fakes_affix import (
    FakeInflClass,
    FakeInflFeature,
    FakeStemName,
    make_infl_entry,
    make_infl_entry_with_slots,
    make_pos,
    make_pos_with_slots,
    make_slot,
    make_source,
)
from _fakes_stem import (
    FakeFeatStruc,
    FakeInflAffMsaOnStem,
    FakeStemInflClass,
    make_stem_entry,
    make_null_form_entry,
)

from gramtrans.Lib.models import GrammarCategory
from gramtrans.Lib.selection import (
    build_deps_inventory,
    build_excluded_lossy_warnings,
    build_pos_grouped_inventory,
    _build_target_sets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_guids(inventory):
    return set(inventory.all_affix_guids())


def _mixed_source():
    """A source with two affixes (verb) and two stems (noun) + one null-form
    stem, all under real POS nodes."""
    pv = make_pos("pv", "v", "Verb")
    pn = make_pos("pn", "n", "Noun")
    a1 = make_infl_entry("a1", "-s", ["3sg"], pv)
    a2 = make_infl_entry("a2", "-ed", ["past"], pv)
    s1 = make_stem_entry("s1", "dog", pn, glosses=["dog"])
    s2 = make_stem_entry("s2", "cat", pn, glosses=["cat"])
    s3 = make_null_form_entry("s3")  # null lexeme form -> stem, junk (no MSA)
    return make_source([a1, a2, s1, s2, s3], [pv, pn])


# ===========================================================================
# T006 — stem inventory build + disjointness + zero-stem empty
# ===========================================================================

class TestBuildStemInventory:

    def test_stem_inventory_lists_only_stems(self):
        src = _mixed_source()
        stem_inv = build_pos_grouped_inventory(src, want_affix=False)
        guids = _all_guids(stem_inv)
        assert "s1" in guids and "s2" in guids
        assert "a1" not in guids and "a2" not in guids

    def test_stem_grouped_by_stem_msa_pos(self):
        src = _mixed_source()
        stem_inv = build_pos_grouped_inventory(src, want_affix=False)
        # Noun POS node carries s1/s2 as inflectional (attaches) rows.
        noun_guids = set()
        for root in stem_inv.roots:
            if root.pos_guid == "pn":
                for row in root.inflectional:
                    noun_guids.add(row.entry_guid)
        assert {"s1", "s2"} <= noun_guids

    def test_disjoint_from_affix_inventory(self):
        src = _mixed_source()
        affix_inv = build_pos_grouped_inventory(src, want_affix=True)
        stem_inv = build_pos_grouped_inventory(src, want_affix=False)
        assert _all_guids(affix_inv).isdisjoint(_all_guids(stem_inv)), (
            "SC-001: an entry must not appear in both tabs"
        )

    def test_null_form_stem_not_dropped(self):
        # s3 has a null lexeme form + no MSA -> lands in stem junk (no_analysis),
        # never dropped from both tabs (FR-002).
        src = _mixed_source()
        stem_inv = build_pos_grouped_inventory(src, want_affix=False)
        assert "s3" in _all_guids(stem_inv)

    def test_zero_stem_source_empty_inventory(self):
        # Only affixes -> stem inventory is empty, not an error (FR-007/SC-006).
        pv = make_pos("pv", "v", "Verb")
        a1 = make_infl_entry("a1", "-s", ["3sg"], pv)
        src = make_source([a1], [pv])
        stem_inv = build_pos_grouped_inventory(src, want_affix=False)
        assert stem_inv.roots == ()
        assert _all_guids(stem_inv) == frozenset()

    def test_affix_inventory_still_lists_only_affixes(self):
        src = _mixed_source()
        affix_inv = build_pos_grouped_inventory(src, want_affix=True)
        guids = _all_guids(affix_inv)
        assert {"a1", "a2"} <= guids
        assert "s1" not in guids and "s2" not in guids


# ===========================================================================
# T011 — MoStemMsa dispatch discipline (FR-013)
# ===========================================================================

class TestStemMsaDispatch:

    def test_stem_msa_never_reads_slots(self):
        # FakeStemMsa.SlotsRC is a tripwire that raises if read. Building the
        # stem inventory must never touch it (FR-013: no cast to IMoInflAffMsa).
        pn = make_pos("pn", "n", "Noun")
        s1 = make_stem_entry("s1", "dog", pn, glosses=["dog"])
        src = make_source([s1], [pn])
        # No exception => SlotsRC was never read.
        stem_inv = build_pos_grouped_inventory(src, want_affix=False)
        assert "s1" in _all_guids(stem_inv)

    def test_non_stem_msa_on_stem_entry_is_skipped(self):
        # A stem-partitioned entry whose ONLY MSA is a MoInflAffMsa must not be
        # recast/placed: it lands in junk (no POS group), never crashes.
        pn = make_pos("pn", "n", "Noun")
        bad = make_stem_entry("sbad", "weird", pn, glosses=["w"],
                              extra_msas=[FakeInflAffMsaOnStem(pn)])
        # Replace the stem entry's MSAs with ONLY the affix MSA.
        bad.MorphoSyntaxAnalysesOC = [FakeInflAffMsaOnStem(pn)]
        src = make_source([bad], [pn])
        stem_inv = build_pos_grouped_inventory(src, want_affix=False)
        # Skipped from POS grouping -> not placed under the Noun node.
        placed = set()
        for root in stem_inv.roots:
            for row in root.inflectional:
                placed.add(row.entry_guid)
        assert "sbad" not in placed
        # But the entry itself is not dropped: it appears in the junk drawer.
        assert "sbad" in _all_guids(stem_inv)

    def test_stem_msa_reads_ms_features_into_deps(self):
        feat = FakeFeatStruc("feat-x", "Aspect")
        pn = make_pos_with_slots("pn", "n", "Noun")
        s1 = make_stem_entry("s1", "dog", pn, glosses=["dog"], ms_features=feat)
        src = make_source([s1], [pn])
        deps = build_deps_inventory(src, frozenset(), stem_picks=frozenset(["s1"]))
        assert "feat-x" in [r.guid for r in deps.infl_features]

    def test_null_inflection_class_is_noop(self):
        # InflectionClassRA is None (Ejagham 0/2444 case): no exception, no dep.
        pn = make_pos_with_slots("pn", "n", "Noun")
        s1 = make_stem_entry("s1", "dog", pn, glosses=["dog"], infl_class=None)
        src = make_source([s1], [pn])
        deps = build_deps_inventory(src, frozenset(), stem_picks=frozenset(["s1"]))
        # No infl class contributed by the stem MSA itself (POS has none either).
        assert deps.infl_classes == []


# ===========================================================================
# T011a — populated InflectionClassRA branch -> FR-009 missing-ref warning
# ===========================================================================

class TestStemInflectionClassPresent:

    def test_populated_infl_class_surfaces_as_dep(self):
        icls = FakeStemInflClass("icls-1", "DeclA")
        pn = make_pos_with_slots("pn", "n", "Noun")
        s1 = make_stem_entry("s1", "dog", pn, glosses=["dog"], infl_class=icls)
        src = make_source([s1], [pn])
        deps = build_deps_inventory(src, frozenset(), stem_picks=frozenset(["s1"]))
        assert "icls-1" in [r.guid for r in deps.infl_classes]

    def test_populated_infl_class_absent_from_target_warns(self):
        # The stem's InflectionClassRA is deselected and absent from target ->
        # exactly one FR-009 warning via build_excluded_lossy_warnings(), and
        # it increments the aggregated count.
        warnings = build_excluded_lossy_warnings(
            affix_slot_map={},
            deselected_slot_guids=set(),
            target_slot_guids=set(),
            deps_by_stem={"s1": {"icls-1": []}},
            deselected_dep_guids={"icls-1"},
            target_dep_guids=set(),  # absent from target
            dep_labels={"icls-1": "DeclA"},
            dep_category=GrammarCategory.INFLECTION_CLASSES,
        )
        assert len(warnings) == 1
        w = warnings[0]
        assert w.category == GrammarCategory.STEMS
        assert w.entry_guid == "s1"
        assert w.dep_guid == "icls-1"

    def test_infl_class_in_target_no_warning(self):
        warnings = build_excluded_lossy_warnings(
            affix_slot_map={},
            deselected_slot_guids=set(),
            target_slot_guids=set(),
            deps_by_stem={"s1": {"icls-1": []}},
            deselected_dep_guids={"icls-1"},
            target_dep_guids={"icls-1"},  # present in target -> LINK, no warning
            dep_labels={"icls-1": "DeclA"},
            dep_category=GrammarCategory.INFLECTION_CLASSES,
        )
        assert warnings == []


# ===========================================================================
# T012 — stem closure + shared-POS GUID dedup across affix and stem picks
# ===========================================================================

class TestStemClosure:

    def test_stem_pulls_pos_dep_collections(self):
        feat = FakeInflFeature("feat-1", "Case")
        cls = FakeInflClass("cls-1", "N1")
        sn = FakeStemName("sn-1", "StemA")
        pn = make_pos_with_slots("pn", "n", "Noun",
                                 infl_feats=[feat], infl_classes=[cls],
                                 stem_names=[sn])
        s1 = make_stem_entry("s1", "dog", pn, glosses=["dog"])
        src = make_source([s1], [pn])
        deps = build_deps_inventory(src, frozenset(), stem_picks=frozenset(["s1"]))
        assert "feat-1" in [r.guid for r in deps.infl_features]
        assert "cls-1" in [r.guid for r in deps.infl_classes]
        assert "sn-1" in [r.guid for r in deps.stem_names]

    def test_shared_pos_deduped_across_affix_and_stem(self):
        # A verb POS whose feature is needed by both a picked affix and a picked
        # stem must be pulled once (deduplicated by GUID).
        feat = FakeInflFeature("feat-shared", "Tense")
        pv = make_pos_with_slots("pv", "v", "Verb", infl_feats=[feat])
        slot = make_slot("slot-1", "S")
        affix = make_infl_entry_with_slots("a1", "-s", ["3sg"], pv, [slot])
        stem = make_stem_entry("s1", "run", pv, glosses=["run"])
        src = make_source([affix, stem], [pv])
        deps = build_deps_inventory(
            src, frozenset(["a1"]), stem_picks=frozenset(["s1"]))
        shared = [r for r in deps.infl_features if r.guid == "feat-shared"]
        assert len(shared) == 1, "shared POS feature must be pulled once"

    def test_deselected_stem_drops_its_deps(self):
        # T013: a POS dep pulled solely on a stem's account disappears when the
        # stem is not in stem_picks (and no kept item needs it).
        feat_n = FakeInflFeature("feat-n", "Case")
        pn = make_pos_with_slots("pn", "n", "Noun", infl_feats=[feat_n])
        s1 = make_stem_entry("s1", "dog", pn, glosses=["dog"])
        src = make_source([s1], [pn])
        with_pick = build_deps_inventory(src, frozenset(), stem_picks=frozenset(["s1"]))
        without_pick = build_deps_inventory(src, frozenset(), stem_picks=frozenset())
        assert "feat-n" in [r.guid for r in with_pick.infl_features]
        assert "feat-n" not in [r.guid for r in without_pick.infl_features]

    def test_dep_kept_when_another_item_needs_it(self):
        feat = FakeInflFeature("feat-shared", "Tense")
        pv = make_pos_with_slots("pv", "v", "Verb", infl_feats=[feat])
        slot = make_slot("slot-1", "S")
        affix = make_infl_entry_with_slots("a1", "-s", ["3sg"], pv, [slot])
        stem = make_stem_entry("s1", "run", pv, glosses=["run"])
        src = make_source([affix, stem], [pv])
        # Drop the stem but keep the affix: the shared feature is still pulled.
        deps = build_deps_inventory(src, frozenset(["a1"]), stem_picks=frozenset())
        assert "feat-shared" in [r.guid for r in deps.infl_features]


# ===========================================================================
# T019 — missing-reference aggregation (one dialog, per-stem entries)
# ===========================================================================

class TestStemMissingRefAggregation:

    def test_one_warning_per_stem_dep(self):
        warnings = build_excluded_lossy_warnings(
            affix_slot_map={},
            deselected_slot_guids=set(),
            target_slot_guids=set(),
            deps_by_stem={"s1": {"pos-x": []}, "s2": {"pos-x": []}},
            deselected_dep_guids={"pos-x"},
            target_dep_guids=set(),
            dep_labels={"pos-x": "Noun"},
            dep_category=GrammarCategory.POS,
        )
        # Two kept stems each strand the same dep -> two entry-centric warnings,
        # but they aggregate into ONE list (one Move confirmation).
        assert len(warnings) == 2
        assert all(w.category == GrammarCategory.STEMS for w in warnings)
        assert {w.entry_guid for w in warnings} == {"s1", "s2"}

    def test_affix_and_stem_warnings_aggregate_together(self):
        warnings = build_excluded_lossy_warnings(
            affix_slot_map={},
            deselected_slot_guids=set(),
            target_slot_guids=set(),
            deps_by_affix={"a1": {"pos-x": []}},
            deps_by_stem={"s1": {"pos-x": []}},
            deselected_dep_guids={"pos-x"},
            target_dep_guids=set(),
            dep_labels={"pos-x": "Noun"},
            dep_category=GrammarCategory.POS,
        )
        cats = {w.category for w in warnings}
        assert cats == {GrammarCategory.AFFIXES, GrammarCategory.STEMS}
        assert len(warnings) == 2  # single combined list


# ===========================================================================
# T021 — target status for stems via _build_target_sets(want_affix=False)
# ===========================================================================

class TestStemTargetStatus:

    def test_self_target_all_in_target(self):
        src = _mixed_source()
        stem_inv = build_pos_grouped_inventory(src, target=src, want_affix=False)
        statuses = []
        for root in stem_inv.roots:
            for row in root.inflectional:
                statuses.append(row.status)
        assert statuses, "expected at least one stem row"
        assert all(st == "in_target" for st in statuses)

    def test_fresh_target_all_new(self):
        src = _mixed_source()
        # A target with only affixes (disjoint GUIDs/forms) -> stems read NEW.
        pv = make_pos("pv", "v", "Verb")
        tgt = make_source([make_infl_entry("ta", "-x", ["g"], pv)], [pv])
        stem_inv = build_pos_grouped_inventory(src, target=tgt, want_affix=False)
        statuses = []
        for root in stem_inv.roots:
            for row in root.inflectional:
                statuses.append(row.status)
        assert statuses
        assert all(st == "new" for st in statuses)

    def test_no_target_status_blank(self):
        src = _mixed_source()
        stem_inv = build_pos_grouped_inventory(src, target=None, want_affix=False)
        for root in stem_inv.roots:
            for row in root.inflectional:
                assert row.status is None

    def test_build_target_sets_partition_selects_stems(self):
        src = _mixed_source()
        affix_guids, _f, _c, _cand = _build_target_sets(src, want_affix=True)
        stem_guids, _f2, _c2, _cand2 = _build_target_sets(src, want_affix=False)
        assert "a1" in affix_guids and "a1" not in stem_guids
        assert "s1" in stem_guids and "s1" not in affix_guids
