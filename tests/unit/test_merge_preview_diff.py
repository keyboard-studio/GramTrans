"""Tests for feature 012 — User Story 1: diff_props mode x value-shape matrix.

Covers T009–T016 (plus T015a):
- NEW mode: all-added across every value shape.
- OVERWRITE mode: multistring / plain str / list-tuple-set / scalar / other-object.
- MERGE-KEEP mode: per-ws emptiness, target-wins semantics.
- LINK-ONLY mode: target unchanged, source-only note.
- Target-only key invariant (never implies deletion).
- Field ordering: alphabetical by field_name (SC-003).

All tests are pure — no Qt, no LCM.
"""

from __future__ import annotations

import pytest

from gramtrans.Lib.merge_preview import (
    LINK_ONLY,
    MERGE_KEEP,
    NEW,
    OVERWRITE,
    MergePreview,
    SegmentKind,
    diff_props,
)
from gramtrans.Lib.ws_fonts import WsRole


def _no_role(_wid):
    return None


def _role_of(wid):
    if wid == "koh":
        return WsRole.VERNACULAR
    if "fonipa" in wid.split("-"):
        return WsRole.IPA
    return WsRole.ANALYSIS


# ============================================================================
# T009 — NEW mode: every value shape → all added (SC-001)
# ============================================================================


class TestNewMode:
    def test_new_mode_multistring(self):
        src = {"CitationForm": {"en": "hello", "koh": "helo"}}
        result = diff_props(src, None, NEW, _role_of)
        assert isinstance(result, MergePreview)
        for fd in result.fields:
            for seg in fd.segments:
                assert (
                    seg.kind == SegmentKind.ADDED
                ), f"Expected ADDED, got {seg.kind} for {fd.field_name}"

    def test_new_mode_plain_str(self):
        src = {"Gloss": "a word"}
        result = diff_props(src, None, NEW, _no_role)
        for fd in result.fields:
            for seg in fd.segments:
                assert seg.kind == SegmentKind.ADDED

    def test_new_mode_list(self):
        src = {"Tags": ["a", "b", "c"]}
        result = diff_props(src, None, NEW, _no_role)
        for fd in result.fields:
            for seg in fd.segments:
                assert seg.kind == SegmentKind.ADDED

    def test_new_mode_scalar_int(self):
        src = {"Count": 42}
        result = diff_props(src, None, NEW, _no_role)
        for fd in result.fields:
            for seg in fd.segments:
                assert seg.kind == SegmentKind.ADDED

    def test_new_mode_scalar_none(self):
        src = {"NullField": None}
        result = diff_props(src, None, NEW, _no_role)
        # None scalar: added segment with repr
        for fd in result.fields:
            for seg in fd.segments:
                assert seg.kind == SegmentKind.ADDED

    def test_new_mode_zero_non_added(self):
        """SC-001: 0 non-added segments across all shapes."""
        src = {
            "A": {"en": "x"},
            "B": "plain",
            "C": [1, 2],
            "D": 99,
            "E": None,
        }
        result = diff_props(src, None, NEW, _no_role)
        non_added = [
            seg for fd in result.fields for seg in fd.segments if seg.kind != SegmentKind.ADDED
        ]
        assert non_added == [], f"Found non-added segments: {non_added}"


# ============================================================================
# T010 — Multistring dispatch (3 assertions: src-only ws, tgt-only ws, differing)
# ============================================================================


class TestMultistringDispatch:
    def test_source_only_ws_added(self):
        """Source-only ws → added."""
        src = {"Form": {"en": "source_en", "koh": "source_koh"}}
        tgt = {"Form": {"en": "tgt_en"}}
        result = diff_props(src, tgt, OVERWRITE, _role_of)
        fd = next(f for f in result.fields if f.field_name == "Form")
        koh_segs = [s for s in fd.segments if "[koh]" in s.text]
        assert any(s.kind == SegmentKind.ADDED for s in koh_segs), "koh (source-only) must be ADDED"

    def test_target_only_ws_unchanged(self):
        """Target-only ws → unchanged (conflict.py L188-190 one-sided-key pass-through)."""
        src = {"Form": {"en": "source_en"}}
        tgt = {"Form": {"en": "tgt_en", "koh": "tgt_koh"}}
        result = diff_props(src, tgt, OVERWRITE, _role_of)
        fd = next(f for f in result.fields if f.field_name == "Form")
        koh_segs = [s for s in fd.segments if "[koh]" in s.text]
        assert any(
            s.kind == SegmentKind.UNCHANGED for s in koh_segs
        ), "koh (tgt-only) must be UNCHANGED"

    def test_differing_ws_removed_and_added(self):
        """Both sides differ for a ws → removed + added; no run-id marker in preview."""
        src = {"Form": {"en": "new_form"}}
        tgt = {"Form": {"en": "old_form"}}
        result = diff_props(src, tgt, OVERWRITE, _role_of)
        fd = next(f for f in result.fields if f.field_name == "Form")
        en_segs = [s for s in fd.segments if "[en]" in s.text]
        kinds = {s.kind for s in en_segs}
        assert SegmentKind.REMOVED in kinds
        assert SegmentKind.ADDED in kinds
        # No run-id marker leaked
        for s in en_segs:
            assert "--- merged" not in s.text

    def test_no_run_id_marker(self):
        """Plain-string diff has no run-id concat marker."""
        src = {"Note": "source note"}
        tgt = {"Note": "target note"}
        result = diff_props(src, tgt, OVERWRITE, _no_role)
        for fd in result.fields:
            for seg in fd.segments:
                assert "--- merged" not in seg.text


# ============================================================================
# T011 — MERGE-KEEP × multistring, mixed empty/non-empty target ws
# ============================================================================


class TestMergeKeepMultistring:
    def test_mix_target_wins_and_added(self):
        """T011: target en non-empty → unchanged+note; target koh empty → added (FR-004a)."""
        src = {"Form": {"en": "other", "koh": "fill"}}
        tgt = {"Form": {"en": "text", "koh": ""}}
        result = diff_props(src, tgt, MERGE_KEEP, _role_of)
        fd = next(f for f in result.fields if f.field_name == "Form")

        en_segs = [s for s in fd.segments if "[en]" in s.text]
        koh_segs = [s for s in fd.segments if "[koh]" in s.text]

        # en: target has value, source differs → target unchanged + note
        unchanged_en = [s for s in en_segs if s.kind == SegmentKind.UNCHANGED]
        note_en = [s for s in fd.segments if s.kind == SegmentKind.NOTE and "en" in s.text]
        assert unchanged_en, "en unchanged segment expected (target wins)"
        assert note_en, "note segment expected for en (source not applied)"

        # koh: target empty → added
        assert any(s.kind == SegmentKind.ADDED for s in koh_segs), "koh empty → ADDED"


# ============================================================================
# T012 — MERGE-KEEP empty-check both forms (absent key AND empty string)
# ============================================================================


class TestMergeKeepEmptyCheck:
    def test_absent_ws_key_is_empty(self):
        """Absent ws key treated as empty target (FR-004a)."""
        src = {"Form": {"en": "source", "koh": "fill"}}
        tgt = {"Form": {"en": "existing"}}  # koh absent
        result = diff_props(src, tgt, MERGE_KEEP, _role_of)
        fd = next(f for f in result.fields if f.field_name == "Form")
        koh_segs = [s for s in fd.segments if "[koh]" in s.text]
        assert any(s.kind == SegmentKind.ADDED for s in koh_segs), "Absent ws → ADDED"

    def test_empty_string_value_is_empty(self):
        """Empty string target value treated as empty (FR-004a)."""
        src = {"Form": {"en": "source", "koh": "fill"}}
        tgt = {"Form": {"en": "", "koh": ""}}  # both empty strings
        result = diff_props(src, tgt, MERGE_KEEP, _role_of)
        fd = next(f for f in result.fields if f.field_name == "Form")
        added = [s for s in fd.segments if s.kind == SegmentKind.ADDED]
        assert len(added) >= 2, "Both empty-string ws → ADDED"


# ============================================================================
# T013 — LINK-ONLY × multistring source-only field emits note (FR-003)
# ============================================================================


class TestLinkOnly:
    def test_source_only_multistring_note(self):
        """T013: source-only multistring field emits a note even when multistring-valued."""
        src = {"NewField": {"en": "value"}}
        tgt = {"ExistingField": "exists"}
        result = diff_props(src, tgt, LINK_ONLY, _no_role)
        # source-only field
        new_fd = next(f for f in result.fields if f.field_name == "NewField")
        assert any(
            s.kind == SegmentKind.NOTE for s in new_fd.segments
        ), "Source-only field must emit a NOTE in LINK_ONLY"
        assert any("not transferred" in s.text for s in new_fd.segments)

    def test_target_fields_unchanged(self):
        """LINK_ONLY: target-present fields are unchanged."""
        src = {}
        tgt = {"F1": "v1", "F2": "v2"}
        result = diff_props(src, tgt, LINK_ONLY, _no_role)
        for fd in result.fields:
            for seg in fd.segments:
                assert seg.kind in (
                    SegmentKind.UNCHANGED,
                ), f"Expected UNCHANGED in LINK_ONLY, got {seg.kind}"


# ============================================================================
# T014 — Target-only key invariant + both-absent not emitted
# ============================================================================


class TestTargetOnlyKeyInvariant:
    @pytest.mark.parametrize("mode", [OVERWRITE, MERGE_KEEP, LINK_ONLY])
    def test_target_only_key_is_unchanged(self, mode):
        """Target-only key → UNCHANGED (never implies deletion) across all modes."""
        src = {}
        tgt = {"TargetOnly": "value"}
        result = diff_props(src, tgt, mode, _no_role)
        fd = next((f for f in result.fields if f.field_name == "TargetOnly"), None)
        assert fd is not None, "Target-only field must be emitted"
        assert all(
            s.kind == SegmentKind.UNCHANGED for s in fd.segments
        ), f"Target-only key must be UNCHANGED in mode {mode}"

    def test_both_absent_not_emitted(self):
        """Keys absent on both sides are NOT emitted."""
        src = {"A": "x"}
        tgt = {"A": "x"}
        result = diff_props(src, tgt, OVERWRITE, _no_role)
        field_names = {fd.field_name for fd in result.fields}
        assert "B" not in field_names  # B is absent on both sides


# ============================================================================
# T015 — Scalar + other-object repr fallback
# ============================================================================


class TestScalarAndReprFallback:
    def test_differing_int_removed_added(self):
        """Differing int → removed + added."""
        src = {"Count": 10}
        tgt = {"Count": 5}
        result = diff_props(src, tgt, OVERWRITE, _no_role)
        fd = next(f for f in result.fields if f.field_name == "Count")
        kinds = {s.kind for s in fd.segments}
        assert SegmentKind.REMOVED in kinds
        assert SegmentKind.ADDED in kinds

    def test_differing_bool_removed_added(self):
        src = {"Flag": True}
        tgt = {"Flag": False}
        result = diff_props(src, tgt, OVERWRITE, _no_role)
        fd = next(f for f in result.fields if f.field_name == "Flag")
        kinds = {s.kind for s in fd.segments}
        assert SegmentKind.REMOVED in kinds
        assert SegmentKind.ADDED in kinds

    def test_none_scalar(self):
        src = {"Field": 42}
        tgt = {"Field": None}
        result = diff_props(src, tgt, OVERWRITE, _no_role)
        fd = next(f for f in result.fields if f.field_name == "Field")
        kinds = {s.kind for s in fd.segments}
        assert SegmentKind.ADDED in kinds

    def test_other_object_repr_fallback(self):
        """Arbitrary object value exercises the repr() fallback branch."""

        class Weird:
            def __repr__(self):
                return "<Weird>"

        src = {"Obj": Weird()}
        tgt = {"Obj": Weird()}
        result = diff_props(src, tgt, OVERWRITE, _no_role)
        fd = next(f for f in result.fields if f.field_name == "Obj")
        # repr fallback should produce segments (added and/or removed based on equality)
        assert len(fd.segments) > 0


# ============================================================================
# T015a — Plain-string + list/tuple/set shapes (closes SC-002 matrix)
# ============================================================================


class TestPlainStrAndSequences:
    def test_plain_str_differing_overwrite(self):
        """Differing plain str → removed + added (no run-id marker)."""
        src = {"Note": "src text"}
        tgt = {"Note": "tgt text"}
        result = diff_props(src, tgt, OVERWRITE, _no_role)
        fd = next(f for f in result.fields if f.field_name == "Note")
        kinds = {s.kind for s in fd.segments}
        assert SegmentKind.REMOVED in kinds
        assert SegmentKind.ADDED in kinds
        for s in fd.segments:
            assert "--- merged" not in s.text

    def test_plain_str_differing_merge_keep(self):
        """MERGE-KEEP differing plain str: target unchanged + note."""
        src = {"Note": "src text"}
        tgt = {"Note": "tgt text"}
        result = diff_props(src, tgt, MERGE_KEEP, _no_role)
        fd = next(f for f in result.fields if f.field_name == "Note")
        kinds = {s.kind for s in fd.segments}
        assert SegmentKind.UNCHANGED in kinds
        assert SegmentKind.NOTE in kinds

    def test_list_union_overwrite(self):
        """List union: common unchanged, source-only added, target-only unchanged."""
        src = {"Tags": ["a", "b", "c"]}
        tgt = {"Tags": ["b", "c", "d"]}
        result = diff_props(src, tgt, OVERWRITE, _no_role)
        fd = next(f for f in result.fields if f.field_name == "Tags")
        a_segs = [s for s in fd.segments if "'a'" in s.text]
        b_segs = [s for s in fd.segments if "'b'" in s.text]
        d_segs = [s for s in fd.segments if "'d'" in s.text]
        assert any(s.kind == SegmentKind.ADDED for s in a_segs), "'a' is source-only → ADDED"
        assert any(s.kind == SegmentKind.UNCHANGED for s in b_segs), "'b' is common → UNCHANGED"
        assert any(
            s.kind == SegmentKind.UNCHANGED for s in d_segs
        ), "'d' is target-only → UNCHANGED"

    def test_set_union_merge_keep(self):
        """Set union in MERGE-KEEP: source-only items added (fill gaps)."""
        src = {"Tags": {"x", "y"}}
        tgt = {"Tags": {"y", "z"}}
        result = diff_props(src, tgt, MERGE_KEEP, _no_role)
        fd = next(f for f in result.fields if f.field_name == "Tags")
        assert len(fd.segments) > 0

    def test_tuple_source_only_added(self):
        src = {"Items": ("new",)}
        tgt = {"Items": ()}
        result = diff_props(src, tgt, OVERWRITE, _no_role)
        fd = next(f for f in result.fields if f.field_name == "Items")
        assert any(s.kind == SegmentKind.ADDED for s in fd.segments)


# ============================================================================
# T016 — Field ordering: alphabetical by field_name in every mode (SC-003)
# ============================================================================


class TestFieldOrdering:
    @pytest.mark.parametrize("mode", [NEW, LINK_ONLY, OVERWRITE, MERGE_KEEP])
    def test_alphabetical_ordering(self, mode):
        """Fields sorted alphabetically in every mode (FR-006, SC-003)."""
        src = {"Zebra": "z", "Apple": "a", "Mango": "m"}
        tgt = {"Zebra": "old_z", "Apple": "a", "Mango": "old_m"}
        tgt_arg = None if mode == NEW else tgt
        result = diff_props(src, tgt_arg, mode, _no_role)
        names = [fd.field_name for fd in result.fields]
        assert names == sorted(names), f"Fields not sorted in mode {mode}: {names}"
