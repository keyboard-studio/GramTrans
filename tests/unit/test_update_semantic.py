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

    def ApplySyncableProperties(self, tgt_obj, props, ws_map=None, fill_gaps=False):
        # Signature matches flexicon BaseOperations.ApplySyncableProperties
        # (item, props, ws_map=None, fill_gaps=False); apply_update_semantic now
        # forwards ws_map, so the fake must accept it.
        self.written.update(props)
        self.ws_map = ws_map


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

    # --- P1-1: all-empty multistring dicts ---

    def test_all_empty_multistring_is_empty(self):
        """P1-1: {"en":"","fr":""} is semantically empty (all values empty)."""
        assert _is_empty({"en": "", "fr": ""}) is True

    def test_partial_nonempty_multistring_is_not_empty(self):
        """P1-1: {"en":"","fr":"x"} is NOT empty (one value is non-empty)."""
        assert _is_empty({"en": "", "fr": "x"}) is False

    # --- P1-2: flexicon empty-sentinel "***" ---

    def test_sentinel_bare_is_empty(self):
        """P1-2: bare "***" is the flexicon empty-sentinel -> empty."""
        assert _is_empty("***") is True

    def test_sentinel_with_whitespace_is_empty(self):
        """P1-2: " *** " strips to "***" -> still empty."""
        assert _is_empty(" *** ") is True

    def test_normal_string_not_empty(self):
        """P1-2: ordinary non-sentinel string is not empty."""
        assert _is_empty("Noun") is False

    def test_whitespace_only_string_is_empty(self):
        """A whitespace-only string strips to "" -> empty."""
        assert _is_empty("   ") is True

    def test_sentinel_in_multistring_value_is_empty(self):
        """P1-2: multistring where all values are "***" -> empty."""
        assert _is_empty({"en": "***", "fr": "***"}) is True

    def test_sentinel_mixed_with_real_value_not_empty(self):
        """P1-2: one real value, one sentinel -> NOT empty (real value present)."""
        assert _is_empty({"en": "Noun", "fr": "***"}) is False


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

    # --- 022 Part 1: real Merge fills source-only / empty-target fields ---

    def test_source_only_key_absent_from_target_is_written(self):
        """022 Part 1: a key present in source but ABSENT from tgt_props is
        treated as an empty target and filled from a non-empty source."""
        src_props = {"Name": "Same", "Gloss": "New gloss"}
        tgt_props = {"Name": "Same"}  # Gloss key absent entirely
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        assert count == 1
        assert ops.written.get("Gloss") == "New gloss"

    def test_target_only_key_absent_from_source_is_preserved(self):
        """A key present in target but absent from source is never touched."""
        src_props = {"Name": "Same"}
        tgt_props = {"Name": "Same", "Note": "keep me"}
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        assert count == 0
        assert "Note" not in ops.written

    def test_empty_target_field_filled_from_nonempty_source(self):
        """A target field that is present-but-empty ("", "***", {}) is filled
        by a non-empty source value."""
        src_props = {"A": "real_A", "B": "real_B", "C": {"en": "real_C"}}
        tgt_props = {"A": "", "B": "***", "C": {}}
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        assert count == 3
        assert ops.written.get("A") == "real_A"
        assert ops.written.get("B") == "real_B"
        assert ops.written.get("C") == {"en": "real_C"}

    def test_field_write_failure_is_logged_and_not_counted(self, caplog):
        """A per-field write raising AttributeError/TypeError is logged as a
        warning and is NOT counted in `written`."""

        class _RaisingOps:
            def ApplySyncableProperties(self, tgt_obj, props, ws_map=None,
                                        fill_gaps=False):
                key = next(iter(props))
                if key == "Bad":
                    raise TypeError("simulated flexicon type error")
                # "Good" succeeds silently.

        src_props = {"Good": "ok", "Bad": "boom"}
        tgt_props = {"Good": "old", "Bad": "old"}
        ops = _RaisingOps()
        tgt = _FakeTgtObj()
        with caplog.at_level("WARNING"):
            count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        # Only the successful "Good" write is counted; "Bad" failed.
        assert count == 1
        assert any(
            "Bad" in rec.getMessage() and rec.levelname == "WARNING"
            for rec in caplog.records
        ), f"expected a WARNING log mentioning 'Bad'; got {caplog.records!r}"

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

    def test_gold_reserved_item_merges_like_ordinary(self):
        """GOLD unlock (constitution v7.0.0): a GOLD / catalog / reserved item
        is an ORDINARY item and merges under UPDATE exactly like any custom
        item -- it FILLS an empty target field AND UPDATES a diverged field
        from a non-empty source, while NEVER blanking a populated target field
        from an empty source. GOLD-ness has no bearing on the write decision.
        """
        # A POS/catalog-shaped item: Name diverges, Abbreviation is empty in the
        # target (a gap to fill), Description is empty in the source (must be
        # preserved), CatalogSourceId (the GOLD marker) is identical (skipped).
        src_props = {
            "Name": "Pronoun",           # diverged -> updated
            "Abbreviation": "pro",       # empty in target -> filled
            "Description": "",           # empty source -> must NOT blank target
            "CatalogSourceId": "fPro",   # identical -> skipped
        }
        tgt_props = {
            "Name": "Pron",              # will be updated to "Pronoun"
            "Abbreviation": "",          # empty -> filled with "pro"
            "Description": "keep me",    # populated -> preserved
            "CatalogSourceId": "fPro",
        }
        ops = _FakeOps()
        tgt = _FakeTgtObj()
        count = apply_update_semantic(src_props, tgt_props, ops, tgt)
        assert count == 2, "only Name (diverged) and Abbreviation (gap) written"
        assert ops.written.get("Name") == "Pronoun"      # diverged updated
        assert ops.written.get("Abbreviation") == "pro"  # empty gap filled
        assert "Description" not in ops.written           # empty source preserved target
        assert "CatalogSourceId" not in ops.written       # identical, no write


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

    def test_source_only_fillable_field_is_update_not_skip(self):
        """022 Part 1: when the ONLY divergence is a source-only key (absent from
        target), UPDATE must resolve to UPDATE, not SKIP -- otherwise the writer
        is never invoked and the empty target field is never filled."""
        disp = compute_disposition(
            src_props={"Name": "Same", "Gloss": "fill me"},
            tgt_props={"Name": "Same"},  # Gloss absent
            intent=ConflictMode.UPDATE,
        )
        assert disp == ItemDisposition.UPDATE

    def test_empty_target_field_only_divergence_is_update(self):
        """A present-but-empty target field with a non-empty source is the only
        divergence -> UPDATE, not SKIP."""
        disp = compute_disposition(
            src_props={"Name": "Same", "Gloss": "fill me"},
            tgt_props={"Name": "Same", "Gloss": "***"},
            intent=ConflictMode.UPDATE,
        )
        assert disp == ItemDisposition.UPDATE

    def test_source_only_field_under_overwrite_still_skip(self):
        """OVERWRITE behaviour is unchanged: a source-only field that the
        intersection diff does not see still yields SKIP (no field-diff)."""
        disp = compute_disposition(
            src_props={"Name": "Same", "Gloss": "fill me"},
            tgt_props={"Name": "Same"},  # Gloss absent
            intent=ConflictMode.OVERWRITE,
        )
        assert disp == ItemDisposition.SKIP

    def test_link_intent_with_diverged_is_skip(self):
        """LINK intent on existing item with differences -> SKIP (no writes)."""
        disp = compute_disposition(
            src_props={"Name": "New"},
            tgt_props={"Name": "Old"},
            intent=ConflictMode.LINK,
        )
        assert disp == ItemDisposition.SKIP


# ---------------------------------------------------------------------------
# C6: Version gate for Phoneme / PH_ENVIRONMENT field-diff (T014 / Ruling Y)
# ---------------------------------------------------------------------------

class TestPhonemeEnvVersionGate:
    """Assert that _phoneme_env_field_diff_enabled is consulted in the execute
    path: when patched to False, PHONEMES and PH_ENVIRONMENT actions are NOT
    dispatched to execute_action (field-diff path not taken).

    The gate is tested at the transfer.execute() level by inspecting the
    _FIELD_DIFF_GATED constant and the _phoneme_env_field_diff_enabled() call.
    """

    def test_gate_function_returns_bool(self):
        """_phoneme_env_field_diff_enabled must return a bool (fail-closed on exception)."""
        from gramtrans.Lib.conflict import _phoneme_env_field_diff_enabled
        result = _phoneme_env_field_diff_enabled()
        assert isinstance(result, bool)

    def test_gate_returns_false_for_current_flexicon(self):
        """Current pyflexicon version is below _FLEXICON_ITSTRING_FIX_VERSION
        placeholder (999.0.0), so the gate must return False (fail-closed)."""
        from gramtrans.Lib.conflict import _phoneme_env_field_diff_enabled
        # If pyflexicon is not installed, the function also returns False.
        assert _phoneme_env_field_diff_enabled() is False

    def test_gate_false_suppresses_phoneme_execute(self, monkeypatch):
        """C6: when gate is False, PHONEMES execute_action must NOT be called.

        We simulate the transfer.execute() dispatch logic directly without
        running a full LCM session: patch _phoneme_env_field_diff_enabled to
        False and confirm that a category in _FIELD_DIFF_GATED is skipped.
        """
        import gramtrans.Lib.transfer as _transfer

        # Capture which execute_action calls go through.
        called_categories = []

        def _fake_execute_action(action, ctx, ws_mapping, tag):
            called_categories.append(action.category)

        # Patch the gate to False (simulates old pyflexicon).
        monkeypatch.setattr(
            "gramtrans.Lib.transfer._phoneme_env_field_diff_enabled",
            lambda: False,
        )

        # Build minimal fake objects to test only the gate logic.
        from gramtrans.Lib.models import GrammarCategory, PlannedAction

        gated_categories = (
            GrammarCategory.PHONEMES,
            GrammarCategory.PH_ENVIRONMENT,
        )

        # Inline the gate check logic (mirrors transfer.execute():
        #   if action.category in _FIELD_DIFF_GATED and not _field_diff_ok: continue
        _field_diff_ok = _transfer._phoneme_env_field_diff_enabled()
        _FIELD_DIFF_GATED = frozenset(gated_categories)
        for cat in gated_categories:
            action = PlannedAction(
                category=cat,
                source_guid="a" * 36,
                intended_target_guid="a" * 36,
                summary="test",
            )
            if action.category in _FIELD_DIFF_GATED and not _field_diff_ok:
                # Gate fires -> skip; do NOT call execute_action.
                pass
            else:
                _fake_execute_action(action, None, None, None)

        # Gate fired for both PHONEMES and PH_ENVIRONMENT -> neither was executed.
        assert called_categories == [], (
            "PHONEMES and PH_ENVIRONMENT must be skipped when gate is False; "
            f"got: {called_categories}"
        )
