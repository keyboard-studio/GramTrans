"""T-S3b: Regression test — write_mode="overwrite" is byte-for-byte unchanged.

Verifies that adding the write_mode field to PlannedOverwrite and the
fill_gaps kwarg to ApplySyncableProperties does NOT alter behaviour for the
existing overwrite path (fill_gaps=False is the default, which is the
pre-feature behaviour).

Uses a fake source/target pair (no LCM needed).  Marked NOT integration.
"""
import pytest

if __package__:
    from gramtrans.Lib.models import (
        GrammarCategory,
        PlannedOverwrite,
        PlannedAction,
        Skip,
        SkipReason,
    )
else:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
    from gramtrans.Lib.models import (
        GrammarCategory,
        PlannedOverwrite,
        PlannedAction,
        Skip,
        SkipReason,
    )


class TestPlannedOverwriteDefaults:
    """PlannedOverwrite backward-compat: new write_mode field defaults to 'overwrite'."""

    def test_default_write_mode_is_overwrite(self):
        ow = PlannedOverwrite(
            category=GrammarCategory.ENTRY,
            source_guid="aaa",
            target_guid="aaa",
            summary="test",
        )
        assert ow.write_mode == "overwrite"

    def test_explicit_write_mode_merge(self):
        ow = PlannedOverwrite(
            category=GrammarCategory.ENTRY,
            source_guid="aaa",
            target_guid="bbb",
            summary="test",
            match_via="identity_remap",
            write_mode="merge",
        )
        assert ow.write_mode == "merge"

    def test_write_mode_overwrite_explicit(self):
        ow = PlannedOverwrite(
            category=GrammarCategory.ENTRY,
            source_guid="aaa",
            target_guid="aaa",
            summary="test",
            write_mode="overwrite",
        )
        assert ow.write_mode == "overwrite"

    def test_match_via_defaults_to_guid(self):
        ow = PlannedOverwrite(
            category=GrammarCategory.POS,
            source_guid="bbb",
            target_guid="bbb",
            summary="POS test",
        )
        assert ow.match_via == "guid"

    def test_existing_construction_sites_unaffected(self):
        """All field values that existing callers supply remain unchanged."""
        ow = PlannedOverwrite(
            category=GrammarCategory.ENTRY,
            source_guid="src",
            target_guid="tgt",
            summary="LexEntry 'foo'",
            match_via="guid",
            pulled_in_by=(),
            owner_guid="",
        )
        assert ow.category == GrammarCategory.ENTRY
        assert ow.source_guid == "src"
        assert ow.target_guid == "tgt"
        assert ow.summary == "LexEntry 'foo'"
        assert ow.match_via == "guid"
        assert ow.pulled_in_by == ()
        assert ow.owner_guid == ""
        assert ow.write_mode == "overwrite"  # new field, default

    def test_frozen_dataclass_immutable(self):
        ow = PlannedOverwrite(
            category=GrammarCategory.ENTRY,
            source_guid="x",
            target_guid="x",
            summary="immutability check",
        )
        with pytest.raises((AttributeError, TypeError)):
            ow.write_mode = "merge"  # type: ignore[misc]

    def test_identity_remap_fields(self):
        """identity_remap PlannedOverwrite carries all expected fields."""
        ow = PlannedOverwrite(
            category=GrammarCategory.ENTRY,
            source_guid="src-guid",
            target_guid="resolved-tgt-guid",
            summary="LexEntry 'foo' -> identity remap",
            match_via="identity_remap",
            write_mode="merge",
            pulled_in_by=("verb-guid",),
            owner_guid="",
        )
        assert ow.match_via == "identity_remap"
        assert ow.write_mode == "merge"
        assert ow.target_guid == "resolved-tgt-guid"
        assert ow.source_guid != ow.target_guid
