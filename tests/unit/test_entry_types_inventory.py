"""T006/T007/T008 -- EntryTypesInventory builder, collapse, and missing-ref tests.

Mirrors test_phonology_inventory.py (spec 010) for the two entry-type categories.
Tests are TDD-ordered: each section is written against an unimplemented function,
then the implementation is added.

Covered:
  T006 - build_entry_types_inventory: groups, counts, preselect, status, hierarchy,
         variant_infl_feat_deps, GUID normalization
  T007 - collapse_entry_types: transfer-all, trimmed subset, whole-block off, empty
  T008 - entry_types_missing_ref_warnings: infl-feat dep chain, resolved refs,
         base entry type (no InflFeatsOA), aggregation
  US3  - GOLD detection via _is_gold_entry_type (catalog_source_id)
  US4  - target-status: in_target, new, similar, None when no target
"""
from __future__ import annotations

import sys
import types
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Minimal SIL.LCModel stub
# ---------------------------------------------------------------------------
_sil = types.ModuleType("SIL")
_lcm = types.ModuleType("SIL.LCModel")
_lcm.ICmObject = None
sys.modules.setdefault("SIL", _sil)
sys.modules.setdefault("SIL.LCModel", _lcm)
_sil.LCModel = _lcm

from gramtrans.Lib.models import GrammarCategory  # noqa: E402
from _fakes_phonology import (  # noqa: E402
    FakeEntryType,
    FakeInflEntryType,
    FakeLexDb,
    FakeLexDbSource,
)

# Import lazily so tests fail clearly if not yet implemented
def _get_builder():
    from gramtrans.Lib.selection import (
        build_entry_types_inventory,
        collapse_entry_types,
        entry_types_missing_ref_warnings,
    )
    return build_entry_types_inventory, collapse_entry_types, entry_types_missing_ref_warnings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_source(*, variants=(), complexes=()):
    lex_db = FakeLexDb(variant_entry_types=variants, complex_entry_types=complexes)
    return FakeLexDbSource(lex_db)


def _simple_target(*, variants=(), complexes=()):
    lex_db = FakeLexDb(variant_entry_types=variants, complex_entry_types=complexes)
    return FakeLexDbSource(lex_db)


# ---------------------------------------------------------------------------
# T006 -- build_entry_types_inventory
# ---------------------------------------------------------------------------

class TestBuildEntryTypesInventory:

    def test_two_groups_in_order(self):
        build, _, _ = _get_builder()
        src = _simple_source(variants=[FakeEntryType("v1", "VT1")],
                              complexes=[FakeEntryType("c1", "CFT1")])
        inv = build(src)
        cats = [g.category for g in inv.groups]
        assert GrammarCategory.VARIANT_TYPES in cats
        assert GrammarCategory.COMPLEX_FORM_TYPES in cats
        # VARIANT_TYPES comes before COMPLEX_FORM_TYPES
        assert cats.index(GrammarCategory.VARIANT_TYPES) < \
               cats.index(GrammarCategory.COMPLEX_FORM_TYPES)

    def test_correct_counts(self):
        build, _, _ = _get_builder()
        vt1 = FakeEntryType("v1", "VT1")
        vt2 = FakeEntryType("v2", "VT2")
        cft1 = FakeEntryType("c1", "CFT1")
        src = _simple_source(variants=[vt1, vt2], complexes=[cft1])
        inv = build(src)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        cft_group = next(g for g in inv.groups
                         if g.category == GrammarCategory.COMPLEX_FORM_TYPES)
        assert vt_group.count == 2
        assert cft_group.count == 1

    def test_all_user_defined_rows_preselected(self):
        build, _, _ = _get_builder()
        vt1 = FakeEntryType("v1", "VT1")
        vt2 = FakeEntryType("v2", "VT2")
        src = _simple_source(variants=[vt1, vt2])
        inv = build(src)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        for row in vt_group.rows:
            assert row.preselected is True

    def test_empty_category_no_error(self):
        build, _, _ = _get_builder()
        src = _simple_source(variants=[], complexes=[FakeEntryType("c1", "CFT1")])
        inv = build(src)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        assert vt_group.rows == () or len(vt_group.rows) == 0

    def test_target_status_in_target_when_guid_matches(self):
        build, _, _ = _get_builder()
        vt1 = FakeEntryType("v1", "VT1")
        src = _simple_source(variants=[vt1])
        tgt = _simple_target(variants=[FakeEntryType("v1", "VT1")])
        inv = build(src, target=tgt)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        row = vt_group.rows[0]
        assert row.status == "in_target"

    def test_target_status_new_when_guid_absent(self):
        build, _, _ = _get_builder()
        vt1 = FakeEntryType("v1", "VT1")
        src = _simple_source(variants=[vt1])
        tgt = _simple_target(variants=[FakeEntryType("other", "Other")])
        inv = build(src, target=tgt)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        row = vt_group.rows[0]
        assert row.status == "new"

    def test_target_status_none_when_no_target(self):
        build, _, _ = _get_builder()
        vt1 = FakeEntryType("v1", "VT1")
        src = _simple_source(variants=[vt1])
        inv = build(src, target=None)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        row = vt_group.rows[0]
        assert row.status is None

    def test_variant_infl_feat_deps_populated(self):
        """An ILexEntryInflType with InflFeatsOA -> value-guid map populated."""
        build, _, _ = _get_builder()
        val_obj = FakeEntryType("val-001", "Feature value")  # fake value ref
        val_obj.guid = "val-001"
        iet = FakeInflEntryType("v-infl", "Inflection Variant",
                                infl_feats=[val_obj])
        src = _simple_source(variants=[iet])
        inv = build(src)
        assert "v-infl" in inv.variant_infl_feat_deps
        assert "val-001" in inv.variant_infl_feat_deps["v-infl"]

    def test_base_entry_type_no_infl_feat_dep(self):
        build, _, _ = _get_builder()
        vt = FakeEntryType("v-base", "Base Variant")
        src = _simple_source(variants=[vt])
        inv = build(src)
        assert "v-base" not in inv.variant_infl_feat_deps

    def test_guid_normalization_raw_guid(self):
        """Mixed-case/braced .Guid on source and target both normalized."""
        build, _, _ = _get_builder()
        normalized = "v1-lower"
        raw = "{V1-LOWER-MIXED}"
        vt_src = FakeEntryType(normalized, "Type A", raw_guid=raw)
        vt_tgt = FakeEntryType(normalized, "Type A", raw_guid=raw)
        src = _simple_source(variants=[vt_src])
        tgt = _simple_target(variants=[vt_tgt])
        inv = build(src, target=tgt)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        assert vt_group.rows[0].status == "in_target"

    # US3 -- GOLD detection
    def test_gold_item_shown_as_in_target(self):
        """GOLD item (catalog_source_id set) shown as in_target when target bound.

        Per spec 021 FR-009 / clarification: GOLD is a cross-referencing device.
        When a target IS bound, GOLD types link to the target's equivalent GOLD
        by identity and are shown as in_target regardless of whether the target
        also carries the same GUID (the engine will Skip(GOLD_INVIOLABLE) at plan
        time; the UI shows the cross-reference so the user understands the link).
        """
        build, _, _ = _get_builder()
        gold_vt = FakeEntryType("gold-v1", "GOLD Type",
                                catalog_source_id="FW-GOLD-001")
        src = _simple_source(variants=[gold_vt])
        # Provide a target (even empty) so status computation runs.
        tgt = _simple_target(variants=[])
        inv = build(src, target=tgt)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        # GOLD type must still appear (not hidden)
        assert len(vt_group.rows) >= 1
        gold_row = next(r for r in vt_group.rows if r.guid == "gold-v1")
        # GOLD is shown as in_target (it is linked to the target's GOLD by identity)
        assert gold_row.status == "in_target"

    def test_non_gold_no_catalog_source_id_is_new(self):
        build, _, _ = _get_builder()
        vt = FakeEntryType("user-v1", "User Type", catalog_source_id=None)
        src = _simple_source(variants=[vt])
        inv = build(src, target=None)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        assert vt_group.rows[0].status is None  # no target -> None

    def test_empty_catalog_source_id_is_not_gold(self):
        build, _, _ = _get_builder()
        vt = FakeEntryType("user-v2", "User Type", catalog_source_id="")
        src = _simple_source(variants=[vt])
        tgt = _simple_target(variants=[])
        inv = build(src, target=tgt)
        vt_group = next(g for g in inv.groups
                        if g.category == GrammarCategory.VARIANT_TYPES)
        assert vt_group.rows[0].status == "new"


# ---------------------------------------------------------------------------
# T007 -- collapse_entry_types
# ---------------------------------------------------------------------------

class TestCollapseEntryTypes:

    def test_all_checked_no_leaf_item_picks_keys(self):
        """All items checked => categories on, no leaf_item_picks key (transfer-all)."""
        build, collapse, _ = _get_builder()
        vt1 = FakeEntryType("v1", "VT1")
        vt2 = FakeEntryType("v2", "VT2")
        cft1 = FakeEntryType("c1", "CFT1")
        src = _simple_source(variants=[vt1, vt2], complexes=[cft1])
        inv = build(src)
        # Build checked_by_category: all guids per category
        checked = {
            GrammarCategory.VARIANT_TYPES: {"v1", "v2"},
            GrammarCategory.COMPLEX_FORM_TYPES: {"c1"},
        }
        result = collapse(inv, checked)
        assert result["categories"].get(GrammarCategory.VARIANT_TYPES) is True
        assert result["categories"].get(GrammarCategory.COMPLEX_FORM_TYPES) is True
        # transfer-all => no leaf_item_picks keys for fully-checked categories
        assert GrammarCategory.VARIANT_TYPES not in result["leaf_item_picks"]
        assert GrammarCategory.COMPLEX_FORM_TYPES not in result["leaf_item_picks"]

    def test_trimmed_category_emits_subset_picks(self):
        build, collapse, _ = _get_builder()
        vt1 = FakeEntryType("v1", "VT1")
        vt2 = FakeEntryType("v2", "VT2")
        src = _simple_source(variants=[vt1, vt2])
        inv = build(src)
        checked = {
            GrammarCategory.VARIANT_TYPES: {"v1"},  # v2 deselected
        }
        result = collapse(inv, checked)
        assert result["categories"].get(GrammarCategory.VARIANT_TYPES) is True
        picks = result["leaf_item_picks"].get(GrammarCategory.VARIANT_TYPES)
        assert picks is not None
        assert "v1" in picks
        assert "v2" not in picks

    def test_whole_block_off_no_categories_no_picks(self):
        build, collapse, _ = _get_builder()
        vt1 = FakeEntryType("v1", "VT1")
        src = _simple_source(variants=[vt1])
        inv = build(src)
        checked = {}  # nothing checked
        result = collapse(inv, checked)
        assert GrammarCategory.VARIANT_TYPES not in result["categories"]
        assert GrammarCategory.COMPLEX_FORM_TYPES not in result["categories"]
        assert result["leaf_item_picks"] == {}

    def test_empty_block_nothing_planned(self):
        build, collapse, _ = _get_builder()
        src = _simple_source(variants=[], complexes=[])
        inv = build(src)
        result = collapse(inv, {})
        assert result["categories"] == {}
        assert result["leaf_item_picks"] == {}


# ---------------------------------------------------------------------------
# T008 -- entry_types_missing_ref_warnings
# ---------------------------------------------------------------------------

class TestEntryTypesMissingRefWarnings:

    def test_infl_type_with_absent_ref_yields_one_warning(self):
        build, collapse, warn = _get_builder()
        val_obj = FakeEntryType("val-001", "Feat val")
        val_obj.guid = "val-001"
        iet = FakeInflEntryType("v-infl", "Infl Variant", infl_feats=[val_obj])
        src = _simple_source(variants=[iet])
        inv = build(src)
        # Target has NO inflection features: val-001 absent
        tgt = _simple_target(variants=[])
        checked = {GrammarCategory.VARIANT_TYPES: {"v-infl"}}
        warnings = warn(inv, checked, target=tgt)
        assert len(warnings) == 1

    def test_infl_type_with_resolved_ref_no_warning(self):
        """If the infl-feat value is present in target, no warning."""
        build, collapse, warn = _get_builder()
        # We simulate a target that 'has' the feature value by providing it
        # in a mock way. Since our builder checks the target's INFLECTION_FEATURES
        # via the selection context, we need to simulate resolution.
        val_obj = FakeEntryType("val-001", "Feat val")
        val_obj.guid = "val-001"
        iet = FakeInflEntryType("v-infl", "Infl Variant", infl_feats=[val_obj])
        src = _simple_source(variants=[iet])
        inv = build(src)
        checked = {GrammarCategory.VARIANT_TYPES: {"v-infl"}}
        # Pass target_infl_feat_guids containing the value guid => resolves
        warnings = warn(inv, checked, target=None,
                        target_infl_feat_guids=frozenset(["val-001"]))
        assert len(warnings) == 0

    def test_base_entry_type_no_infl_feats_no_warning(self):
        build, collapse, warn = _get_builder()
        vt = FakeEntryType("v-base", "Base Variant")
        src = _simple_source(variants=[vt])
        inv = build(src)
        checked = {GrammarCategory.VARIANT_TYPES: {"v-base"}}
        warnings = warn(inv, checked, target=None)
        assert len(warnings) == 0

    def test_unchecked_infl_type_no_warning(self):
        """An unchecked inflection type does NOT generate a warning."""
        build, collapse, warn = _get_builder()
        val_obj = FakeEntryType("val-001", "Feat val")
        val_obj.guid = "val-001"
        iet = FakeInflEntryType("v-infl", "Infl Variant", infl_feats=[val_obj])
        src = _simple_source(variants=[iet])
        inv = build(src)
        checked = {}  # nothing checked -- block off
        warnings = warn(inv, checked, target=None)
        assert len(warnings) == 0

    def test_multiple_kept_infl_types_aggregate(self):
        """N kept inflection types with absent refs => N warnings."""
        build, collapse, warn = _get_builder()
        val1 = FakeEntryType("val-001", "Val 1")
        val2 = FakeEntryType("val-002", "Val 2")
        iet1 = FakeInflEntryType("v-infl-1", "Infl Variant 1", infl_feats=[val1])
        iet2 = FakeInflEntryType("v-infl-2", "Infl Variant 2", infl_feats=[val2])
        src = _simple_source(variants=[iet1, iet2])
        inv = build(src)
        checked = {
            GrammarCategory.VARIANT_TYPES: {"v-infl-1", "v-infl-2"}
        }
        warnings = warn(inv, checked, target=None)
        assert len(warnings) == 2
