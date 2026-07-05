"""T016/T019 -- _PageEntryTypes display, whole-block toggle, and collapse tests.

Spec 021 T016 (US1) and T019 (US2) and T025 (US5). Tests run headless (no Qt
event loop) by inspecting the module-level _PageEntryTypes class attributes and
the collapse/missing-ref logic directly via selection.py helpers.

SC-008 guard: assert _PageEntryTypes renders NO ADD_NEW/MERGE/OVERWRITE
conflict-mode control in its _build_ui method (FR-012).
"""
from __future__ import annotations

import sys
import types

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
from gramtrans.Lib.selection import (  # noqa: E402
    build_entry_types_inventory,
    collapse_entry_types,
    entry_types_missing_ref_warnings,
)
from _fakes_phonology import (  # noqa: E402
    FakeEntryType,
    FakeInflEntryType,
    FakeLexDb,
    FakeLexDbSource,
)


def _make_source(*, variants=(), complexes=()):
    lex_db = FakeLexDb(variant_entry_types=variants, complex_entry_types=complexes)
    return FakeLexDbSource(lex_db)


# ---------------------------------------------------------------------------
# T016 (US1) -- preselect-all collapse produces transfer-all, no picks keys
# ---------------------------------------------------------------------------

class TestPreviewCollapsePreselectedAll:

    def test_all_checked_no_leaf_item_picks_keys(self):
        """SC-001/SC-002: preselect-all state -> collapse yields transfer-all."""
        vt1 = FakeEntryType("v1", "VT1")
        vt2 = FakeEntryType("v2", "VT2")
        cft1 = FakeEntryType("c1", "CFT1")
        src = _make_source(variants=[vt1, vt2], complexes=[cft1])
        inv = build_entry_types_inventory(src)
        # Simulate all rows checked (the default preselected state)
        checked = {
            GrammarCategory.VARIANT_TYPES: {"v1", "v2"},
            GrammarCategory.COMPLEX_FORM_TYPES: {"c1"},
        }
        result = collapse_entry_types(inv, checked)
        assert result["categories"].get(GrammarCategory.VARIANT_TYPES) is True
        assert result["categories"].get(GrammarCategory.COMPLEX_FORM_TYPES) is True
        # transfer-all => no leaf_item_picks keys
        assert GrammarCategory.VARIANT_TYPES not in result["leaf_item_picks"]
        assert GrammarCategory.COMPLEX_FORM_TYPES not in result["leaf_item_picks"]

    def test_page_title_contains_of_8(self):
        """FR-001 / SC-007: page title must reflect '8' total pages."""
        pytest.importorskip("PyQt6")
        from gramtrans.Lib.ui.selection_wizard import _PageEntryTypes
        page = _PageEntryTypes()
        title = page.title()
        assert "of 8" in title, f"Expected 'of 8' in title, got: {title!r}"

    def test_page_title_contains_entry_types(self):
        pytest.importorskip("PyQt6")
        from gramtrans.Lib.ui.selection_wizard import _PageEntryTypes
        page = _PageEntryTypes()
        title = page.title()
        # Title should mention entry types (case-insensitive)
        assert "entry" in title.lower() or "types" in title.lower(), (
            f"Expected 'entry' or 'types' in title, got: {title!r}"
        )


class TestNoConflictModeControls:

    def test_no_conflict_mode_qcombobox_in_page(self):
        """SC-008 / FR-012: _PageEntryTypes must have NO conflict-mode combo boxes."""
        pytest.importorskip("PyQt6")
        from PyQt6 import QtWidgets
        from gramtrans.Lib.ui.selection_wizard import _PageEntryTypes

        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication([])

        page = _PageEntryTypes()
        # Find all QComboBox children -- conflict-mode selectors would be QComboBox
        combos = page.findChildren(QtWidgets.QComboBox)
        # None of these should reference ADD_NEW, MERGE, OVERWRITE
        conflict_mode_combos = [
            c for c in combos
            if any(
                word in c.toolTip().upper() or any(
                    word in c.itemText(i).upper()
                    for i in range(c.count())
                )
                for word in ("ADD_NEW", "MERGE", "OVERWRITE")
            )
        ]
        assert conflict_mode_combos == [], (
            f"Found conflict-mode combo boxes in _PageEntryTypes: {conflict_mode_combos}"
        )


# ---------------------------------------------------------------------------
# T019 (US2) -- trim and whole-block off
# ---------------------------------------------------------------------------

class TestCollapseTrimmingAndOff:

    def test_whole_block_off_no_categories(self):
        """SC-003: whole-block off -> no categories, no picks."""
        vt1 = FakeEntryType("v1", "VT1")
        src = _make_source(variants=[vt1])
        inv = build_entry_types_inventory(src)
        result = collapse_entry_types(inv, {})
        assert result["categories"] == {}
        assert result["leaf_item_picks"] == {}

    def test_trim_variant_type_emits_subset_picks(self):
        vt1 = FakeEntryType("v1", "VT1")
        vt2 = FakeEntryType("v2", "VT2")
        src = _make_source(variants=[vt1, vt2])
        inv = build_entry_types_inventory(src)
        # Only v1 kept; v2 deselected
        checked = {GrammarCategory.VARIANT_TYPES: {"v1"}}
        result = collapse_entry_types(inv, checked)
        picks = result["leaf_item_picks"].get(GrammarCategory.VARIANT_TYPES)
        assert picks is not None
        assert "v1" in picks
        assert "v2" not in picks

    def test_all_checked_key_omitted(self):
        """Fully-checked category omits the leaf_item_picks key (transfer-all)."""
        vt1 = FakeEntryType("v1", "VT1")
        src = _make_source(variants=[vt1])
        inv = build_entry_types_inventory(src)
        checked = {GrammarCategory.VARIANT_TYPES: {"v1"}}
        result = collapse_entry_types(inv, checked)
        # Only 1 item, checked -> all checked -> no key
        assert GrammarCategory.VARIANT_TYPES not in result["leaf_item_picks"]

    def test_deselect_sibling_category_group_independent(self):
        """Deselecting variant types does not affect complex form types category."""
        vt1 = FakeEntryType("v1", "VT1")
        cft1 = FakeEntryType("c1", "CFT1")
        src = _make_source(variants=[vt1], complexes=[cft1])
        inv = build_entry_types_inventory(src)
        # Only complex form types checked
        checked = {GrammarCategory.COMPLEX_FORM_TYPES: {"c1"}}
        result = collapse_entry_types(inv, checked)
        assert GrammarCategory.COMPLEX_FORM_TYPES in result["categories"]
        assert GrammarCategory.VARIANT_TYPES not in result["categories"]


# ---------------------------------------------------------------------------
# T025 (US5) -- missing-ref warnings aggregated
# ---------------------------------------------------------------------------

class TestMissingRefWarningsAggregated:

    def test_n_missing_ref_warnings_plus_no_double_dialog(self):
        """SC-006: N missing-ref warnings produce count; resolved ref -> 0."""
        val1 = FakeEntryType("val-001", "Val 1")
        val2 = FakeEntryType("val-002", "Val 2")
        iet1 = FakeInflEntryType("v-infl-1", "Infl Variant 1", infl_feats=[val1])
        iet2 = FakeInflEntryType("v-infl-2", "Infl Variant 2", infl_feats=[val2])
        src = _make_source(variants=[iet1, iet2])
        inv = build_entry_types_inventory(src)
        checked = {GrammarCategory.VARIANT_TYPES: {"v-infl-1", "v-infl-2"}}
        # Both refs absent from target
        warnings = entry_types_missing_ref_warnings(inv, checked, target=None)
        assert len(warnings) == 2  # aggregated, one per kept type

    def test_resolved_ref_no_warning(self):
        val = FakeEntryType("val-001", "Val 1")
        iet = FakeInflEntryType("v-infl-1", "Infl Variant 1", infl_feats=[val])
        src = _make_source(variants=[iet])
        inv = build_entry_types_inventory(src)
        checked = {GrammarCategory.VARIANT_TYPES: {"v-infl-1"}}
        # Resolved in target
        warnings = entry_types_missing_ref_warnings(
            inv, checked, target=None,
            target_infl_feat_guids=frozenset(["val-001"])
        )
        assert len(warnings) == 0

    def test_base_entry_type_no_warning(self):
        vt = FakeEntryType("v-base", "Base Variant")
        src = _make_source(variants=[vt])
        inv = build_entry_types_inventory(src)
        checked = {GrammarCategory.VARIANT_TYPES: {"v-base"}}
        warnings = entry_types_missing_ref_warnings(inv, checked, target=None)
        assert len(warnings) == 0
