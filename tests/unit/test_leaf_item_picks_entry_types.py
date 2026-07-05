"""T002 -- leaf_item_picks filter for VARIANT_TYPES and COMPLEX_FORM_TYPES.

Mirrors tests/unit/test_leaf_item_picks.py (spec 010) for the two entry-type
categories. The filter is the same contract as _phonology_simple_enumerate:

  picks = selection.leaf_picks_for(category)
  if picks is not None:
      records = [r for r in records if _guid_str_from(r) in picks]

Key invariants:
  - Key absent (picks=None) => all items returned (back-compat)
  - Key present with guids => only those guids
  - Empty frozenset => zero items (distinct from picks=None)
  - GUID normalization: mixed-case/braced .Guid on source, normalized picks
  - A leaf_item_picks key for a category with is_on=False is inert
    (the is_on gate in leaf-dispatch fires first)
  - Empty-user-defined-list != picks=None (FR-006 distinction)
"""
from __future__ import annotations

import dataclasses
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Minimal SIL.LCModel stub so categories.py can be imported without pythonnet
# ---------------------------------------------------------------------------
_sil = types.ModuleType("SIL")
_lcm = types.ModuleType("SIL.LCModel")
_lcm.ICmObject = None   # will be unused; _guid_str_from falls back to .guid
sys.modules.setdefault("SIL", _sil)
sys.modules.setdefault("SIL.LCModel", _lcm)
_sil.LCModel = _lcm

# Import categories after stub is registered
from gramtrans.Lib import categories as _cat  # noqa: E402
from gramtrans.Lib.models import GrammarCategory, Selection  # noqa: E402
from _fakes_phonology import (  # noqa: E402
    FakeContext,
    FakeEntryType,
    FakeLexDb,
    FakeLexDbSource,
)


def _make_selection(picks_by_cat=None):
    """Build a Selection with given leaf_item_picks dict (or empty)."""
    picks = picks_by_cat or {}
    return dataclasses.replace(
        Selection(categories={
            GrammarCategory.VARIANT_TYPES: True,
            GrammarCategory.COMPLEX_FORM_TYPES: True,
        }),
        leaf_item_picks=picks,
    )


def _ctx(source):
    return FakeContext(source=source, target=None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vt_enumerate(source, selection):
    ctx = _ctx(source)
    return list(_cat.variant_types_enumerate_source(ctx, selection))


def _cft_enumerate(source, selection):
    ctx = _ctx(source)
    return list(_cat.complex_form_types_enumerate_source(ctx, selection))


# ---------------------------------------------------------------------------
# VARIANT_TYPES
# ---------------------------------------------------------------------------

class TestVariantTypesPicksFilter:

    def _make_source(self, variant_types=()):
        lex_db = FakeLexDb(variant_entry_types=variant_types)
        return FakeLexDbSource(lex_db)

    def test_key_absent_returns_all_items(self):
        vt1 = FakeEntryType("aa-001", "Type A")
        vt2 = FakeEntryType("aa-002", "Type B")
        src = self._make_source([vt1, vt2])
        sel = _make_selection()  # no leaf_item_picks key
        result = _vt_enumerate(src, sel)
        assert len(result) == 2

    def test_key_present_filters_to_subset(self):
        vt1 = FakeEntryType("aa-001", "Type A")
        vt2 = FakeEntryType("aa-002", "Type B")
        vt3 = FakeEntryType("aa-003", "Type C")
        src = self._make_source([vt1, vt2, vt3])
        sel = _make_selection({
            GrammarCategory.VARIANT_TYPES: frozenset(["aa-001", "aa-003"])
        })
        result = _vt_enumerate(src, sel)
        guids = [r.guid for r in result]
        assert "aa-001" in guids
        assert "aa-003" in guids
        assert "aa-002" not in guids

    def test_empty_frozenset_returns_zero_items(self):
        vt1 = FakeEntryType("aa-001", "Type A")
        src = self._make_source([vt1])
        sel = _make_selection({
            GrammarCategory.VARIANT_TYPES: frozenset()
        })
        result = _vt_enumerate(src, sel)
        assert result == []

    def test_guid_normalization_braced_uppercase(self):
        """Picks contain normalized guids; source .Guid is braced + mixed-case."""
        raw = "{AA-001-MIXED}"
        normalized = "aa-001-mixed"
        # _guid_str_from falls back to .guid on fake objects
        vt1 = FakeEntryType(normalized, "Type A", raw_guid=raw)
        src = self._make_source([vt1])
        sel = _make_selection({
            GrammarCategory.VARIANT_TYPES: frozenset([normalized])
        })
        result = _vt_enumerate(src, sel)
        assert len(result) == 1

    def test_empty_user_defined_list_is_not_transfer_all(self):
        """Empty frozenset picks is NOT the same as absent key (FR-006)."""
        vt1 = FakeEntryType("aa-001", "Type A")
        src = self._make_source([vt1])
        # picks=frozenset() vs picks=None
        sel_empty_picks = _make_selection({
            GrammarCategory.VARIANT_TYPES: frozenset()
        })
        sel_no_key = _make_selection()
        assert _vt_enumerate(src, sel_empty_picks) == []
        assert len(_vt_enumerate(src, sel_no_key)) == 1

    def test_gold_item_included_when_picks_none(self):
        """GOLD items are returned when no picks key (transfer-all path)."""
        gold_vt = FakeEntryType("gg-gold", "GOLD Type",
                                catalog_source_id="FW-GOLD-001")
        src = self._make_source([gold_vt])
        sel = _make_selection()
        result = _vt_enumerate(src, sel)
        assert len(result) == 1

    def test_gold_item_filtered_when_not_in_picks(self):
        """GOLD items are filtered out when their guid is not in picks."""
        gold_vt = FakeEntryType("gg-gold", "GOLD Type",
                                catalog_source_id="FW-GOLD-001")
        user_vt = FakeEntryType("uu-user", "User Type")
        src = self._make_source([gold_vt, user_vt])
        sel = _make_selection({
            GrammarCategory.VARIANT_TYPES: frozenset(["uu-user"])
        })
        result = _vt_enumerate(src, sel)
        guids = [r.guid for r in result]
        assert "uu-user" in guids
        assert "gg-gold" not in guids


# ---------------------------------------------------------------------------
# COMPLEX_FORM_TYPES
# ---------------------------------------------------------------------------

class TestComplexFormTypesPicksFilter:

    def _make_source(self, complex_types=()):
        lex_db = FakeLexDb(complex_entry_types=complex_types)
        return FakeLexDbSource(lex_db)

    def test_key_absent_returns_all_items(self):
        cft1 = FakeEntryType("cc-001", "Compound")
        cft2 = FakeEntryType("cc-002", "Idiom")
        src = self._make_source([cft1, cft2])
        sel = _make_selection()
        result = _cft_enumerate(src, sel)
        assert len(result) == 2

    def test_key_present_filters_to_subset(self):
        cft1 = FakeEntryType("cc-001", "Compound")
        cft2 = FakeEntryType("cc-002", "Idiom")
        src = self._make_source([cft1, cft2])
        sel = _make_selection({
            GrammarCategory.COMPLEX_FORM_TYPES: frozenset(["cc-001"])
        })
        result = _cft_enumerate(src, sel)
        assert len(result) == 1
        assert result[0].guid == "cc-001"

    def test_empty_frozenset_returns_zero_items(self):
        cft1 = FakeEntryType("cc-001", "Compound")
        src = self._make_source([cft1])
        sel = _make_selection({
            GrammarCategory.COMPLEX_FORM_TYPES: frozenset()
        })
        assert _cft_enumerate(src, sel) == []

    def test_guid_normalization(self):
        raw = "{CC-001-MIXED}"
        normalized = "cc-001-mixed"
        cft1 = FakeEntryType(normalized, "Compound", raw_guid=raw)
        src = self._make_source([cft1])
        sel = _make_selection({
            GrammarCategory.COMPLEX_FORM_TYPES: frozenset([normalized])
        })
        result = _cft_enumerate(src, sel)
        assert len(result) == 1

    def test_variant_key_does_not_affect_complex_form_types(self):
        """A leaf_item_picks key for VARIANT_TYPES is inert for COMPLEX_FORM_TYPES."""
        cft1 = FakeEntryType("cc-001", "Compound")
        src = self._make_source([cft1])
        # Only VARIANT_TYPES picks specified; COMPLEX_FORM_TYPES key absent
        sel = _make_selection({
            GrammarCategory.VARIANT_TYPES: frozenset(["vv-something"])
        })
        result = _cft_enumerate(src, sel)
        assert len(result) == 1  # all complex form types returned
