"""022-disposition-model T026: Unit tests for the non-destructive UPDATE write semantic.

FR-003: Under UPDATE, source wins on diverged fields; a target field is NEVER
blanked from an empty source.
SC-003: OVERWRITE on the same pair blanks the empty-source field (destructive contrast).

All tests use fake props dicts (no LCM host required).
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.conflict import (
    ItemDisposition,
    apply_update_semantic,
    compute_disposition,
    _is_empty,
)
from gramtrans.Lib.models import ConflictMode, GrammarCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeOps:
    """Fake Operations object that captures ApplySyncableProperties calls."""

    def __init__(self):
        self.written = {}

    def ApplySyncableProperties(self, tgt_obj, props):
        self.written.update(props)


class _FakeTgtObj:
    """Placeholder target LCM object."""
    pass


# ---------------------------------------------------------------------------
# _is_empty helper
# ---------------------------------------------------------------------------

class TestIsEmpty:
    def test_none_is_empty(self):
        assert _is_empty(None) is True

    def test_empty_string(self):
        assert _is_empty("") is True

    def test_nonempty_string(self):
        assert _is_empty("hello") is False

    def test_empty_dict(self):
        assert _is_empty({}) is True

    def test_nonempty_dict(self):
        assert _is_empty({"en": "hello"}) is False

    def test_empty_list(self):
        assert _is_empty([]) is True

    def test_nonempty_list(self):
        assert _is_empty(["x"]) is False

    def test_int_zero_not_empty(self):
        """int 0 is intentional data, not empty."""
        assert _is_empty(0) is False

    def test_bool_false_not_empty(self):
        """bool False is intentional data, not empty."""
        assert _is_empty(False) is False


# ---------------------------------------------------------------------------
# apply_update_semantic
# ---------------------------------------------------------------------------

class TestApplyUpdateSemantic:
    def test_diverged_nonempty_source_field_written(self):
        """(a) Field A differs and source is non-empty -> target takes source value."""
        src_props = {"Name": "Updated Name", "Abbrev": "UPD"}
        tgt_props = {"Name": "Old Name", "Abbrev": "OLD"}
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        assert count == 2
        assert ops.written["Name"] == "Updated Name"
        assert ops.written["Abbrev"] == "UPD"

    def test_empty_source_field_does_not_blank_target(self):
        """(b) FR-003: source is empty -> target field preserved (never blanked)."""
        src_props = {"Name": "Updated", "Description": ""}  # Description is empty in source
        tgt_props = {"Name": "Old", "Description": "Keep me"}
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        # Only Name should be written; Description skipped (source empty)
        assert count == 1
        assert "Name" in ops.written
        assert "Description" not in ops.written

    def test_none_source_field_does_not_blank_target(self):
        """Source field is None -> target preserved."""
        src_props = {"Name": "New", "Gloss": None}
        tgt_props = {"Name": "Old", "Gloss": "Keep"}
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        assert count == 1
        assert ops.written.get("Name") == "New"
        assert "Gloss" not in ops.written

    def test_identical_fields_not_written(self):
        """Identical source and target fields generate no write."""
        src_props = {"Name": "Same", "Abbrev": "S"}
        tgt_props = {"Name": "Same", "Abbrev": "S"}
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        assert count == 0
        assert ops.written == {}

    def test_all_source_empty_nothing_written(self):
        """All source fields empty -> no writes (pure preserve)."""
        src_props = {"Name": "", "Description": None}
        tgt_props = {"Name": "Keep", "Description": "Keep too"}
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        assert count == 0

    def test_mixed_empty_and_diverged(self):
        """Mixed: some source empty (skip), some diverged (write)."""
        src_props = {"A": "new_A", "B": "", "C": "new_C", "D": None}
        tgt_props = {"A": "old_A", "B": "keep_B", "C": "old_C", "D": "keep_D"}
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        assert count == 2  # A and C written
        assert ops.written.get("A") == "new_A"
        assert ops.written.get("C") == "new_C"
        assert "B" not in ops.written
        assert "D" not in ops.written

    def test_overwrite_contrast_would_blank(self):
        """SC-003: OVERWRITE semantics differ -- this test documents the contrast.

        apply_update_semantic (UPDATE) skips empty source fields.
        OVERWRITE would write them unconditionally (blanking target).
        We verify apply_update_semantic does NOT blank B.
        """
        src_props = {"A": "new_A", "B": ""}  # B empty in source
        tgt_props = {"A": "old_A", "B": "keep_B"}
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        apply_update_semantic(src_props, tgt_props, ops, tgt)
        # UPDATE: B must NOT be blanked
        assert "B" not in ops.written, (
            "UPDATE must never blank a target field from an empty source (FR-003)"
        )


# ---------------------------------------------------------------------------
# compute_disposition for UPDATE intent
# ---------------------------------------------------------------------------

class TestComputeDispositionUpdate:
    def test_new_item_always_add(self):
        """Item not present in target -> ADD regardless of intent."""
        disp = compute_disposition(
            src_props={"Name": "X"},
            tgt_props=None,
            intent=ConflictMode.UPDATE,
        )
        assert disp == ItemDisposition.ADD

    def test_identical_item_is_skip(self):
        """All fields identical -> SKIP (no write)."""
        props = {"Name": "Same", "Abbrev": "S"}
        disp = compute_disposition(
            src_props=props,
            tgt_props=props.copy(),
            intent=ConflictMode.UPDATE,
        )
        assert disp == ItemDisposition.SKIP

    def test_diverged_field_is_update(self):
        """>=1 diverged field under UPDATE -> UPDATE disposition."""
        disp = compute_disposition(
            src_props={"Name": "New", "Abbrev": "N"},
            tgt_props={"Name": "Old", "Abbrev": "N"},
            intent=ConflictMode.UPDATE,
        )
        assert disp == ItemDisposition.UPDATE

    def test_diverged_field_under_overwrite_is_overwrite(self):
        """>=1 diverged field under OVERWRITE -> OVERWRITE disposition."""
        disp = compute_disposition(
            src_props={"Name": "New"},
            tgt_props={"Name": "Old"},
            intent=ConflictMode.OVERWRITE,
        )
        assert disp == ItemDisposition.OVERWRITE

    def test_link_intent_with_diverged_is_skip(self):
        """LINK intent on existing item with differences -> SKIP (no writes)."""
        disp = compute_disposition(
            src_props={"Name": "New"},
            tgt_props={"Name": "Old"},
            intent=ConflictMode.LINK,
        )
        assert disp == ItemDisposition.SKIP
