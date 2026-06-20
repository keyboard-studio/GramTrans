"""T014 — round-trip + edge-case tests for the Phase 2 `merge=` segment
extension of ImportResidueTag.

Spec: contracts/residue-merge-segment.md.
"""
from __future__ import annotations

import base64

import pytest

from gramtrans.Lib.models import (
    MergeDecision,
    MergeDecisionLog,
    MergeResolution,
)
from gramtrans.Lib.residue import ImportResidueTag


BASE_TAG = ImportResidueTag(
    run_id="GT-20260620-180000",
    source_project_name="Ejagham Mini",
    timestamp="2026-06-20T18:00:00",
)


def _sample_log():
    return MergeDecisionLog(
        target_guid="15a59768-ad27-4e12-bf9f-719c55854c9f",
        decisions=(
            MergeDecision(
                field_name="Comment",
                resolution=MergeResolution.TAKE_SOURCE,
                left_value="old",
                right_value="new",
            ),
            MergeDecision(
                field_name="Custom_Topic",
                resolution=MergeResolution.MERGE,
                left_value="A",
                right_value="B",
            ),
        ),
    )


# ============================================================================
# Wire format: 4 / 5 / 6 segment forms
# ============================================================================

def test_four_segment_round_trip():
    """Phase 0 tag (no snap=, no merge=) still parses unchanged."""
    s = BASE_TAG.serialize()
    assert s.count("|") == 3
    assert ImportResidueTag.parse(s) == BASE_TAG


def test_five_segment_snap_only_round_trip():
    """Phase 1 tag (snap= only) still parses unchanged."""
    t = BASE_TAG.with_snapshot({"Comment": "old"})
    s = t.serialize()
    assert s.count("|") == 4
    assert "|snap=" in s
    assert "|merge=" not in s
    assert ImportResidueTag.parse(s) == t


def test_five_segment_merge_only_round_trip():
    """Phase 2 tag with merge= but no snap= (FR-215 backward-compat case)."""
    t = BASE_TAG.with_merge_log(_sample_log())
    s = t.serialize()
    assert s.count("|") == 4
    assert "|merge=" in s
    assert "|snap=" not in s
    assert ImportResidueTag.parse(s) == t


def test_six_segment_snap_then_merge_round_trip():
    """Phase 2 tag with both segments."""
    t = BASE_TAG.with_snapshot({"k": "v"}).with_merge_log(_sample_log())
    s = t.serialize()
    assert s.count("|") == 5
    # Ordering: snap= must appear before merge=
    assert s.index("|snap=") < s.index("|merge=")
    parsed = ImportResidueTag.parse(s)
    assert parsed == t
    assert parsed.decode_snapshot() == {"k": "v"}
    assert parsed.decode_merge_log() == _sample_log()


# ============================================================================
# Reject malformed forms
# ============================================================================

def test_parse_rejects_merge_before_snap():
    """`merge=` MUST follow `snap=` if both are present."""
    bad = (
        "GT|GT-20260620-180000|Ejagham Mini|2026-06-20T18:00:00"
        "|merge=AAAA|snap=BBBB"
    )
    assert ImportResidueTag.parse(bad) is None


def test_parse_rejects_double_snap():
    bad = (
        "GT|GT-20260620-180000|Ejagham Mini|2026-06-20T18:00:00"
        "|snap=AAAA|snap=BBBB"
    )
    assert ImportResidueTag.parse(bad) is None


def test_parse_rejects_double_merge():
    bad = (
        "GT|GT-20260620-180000|Ejagham Mini|2026-06-20T18:00:00"
        "|merge=AAAA|merge=BBBB"
    )
    assert ImportResidueTag.parse(bad) is None


def test_parse_rejects_unknown_segment_prefix():
    bad = (
        "GT|GT-20260620-180000|Ejagham Mini|2026-06-20T18:00:00"
        "|extra=AAAA"
    )
    assert ImportResidueTag.parse(bad) is None


def test_parse_rejects_seven_segments():
    bad = (
        "GT|GT-20260620-180000|Ejagham Mini|2026-06-20T18:00:00"
        "|snap=AAAA|merge=BBBB|junk=CCCC"
    )
    assert ImportResidueTag.parse(bad) is None


# ============================================================================
# decode_merge_log: graceful degradation on corruption (FR-215)
# ============================================================================

def test_decode_merge_log_returns_none_without_segment():
    assert BASE_TAG.decode_merge_log() is None
    assert BASE_TAG.with_snapshot({"k": "v"}).decode_merge_log() is None


def test_decode_merge_log_returns_none_on_corrupted_base64():
    corrupt = ImportResidueTag(
        run_id=BASE_TAG.run_id,
        source_project_name=BASE_TAG.source_project_name,
        timestamp=BASE_TAG.timestamp,
        merge_b64="!!!not_base64!!!",
    )
    assert corrupt.decode_merge_log() is None


def test_decode_merge_log_returns_none_on_invalid_json():
    junk_b64 = base64.b64encode(b"{not valid json}").decode("ascii")
    corrupt = ImportResidueTag(
        run_id=BASE_TAG.run_id,
        source_project_name=BASE_TAG.source_project_name,
        timestamp=BASE_TAG.timestamp,
        merge_b64=junk_b64,
    )
    assert corrupt.decode_merge_log() is None


def test_decode_merge_log_returns_none_on_schema_mismatch():
    """Valid JSON but missing required fields -> None per FR-215."""
    schema_bad_b64 = base64.b64encode(b'{"foo": "bar"}').decode("ascii")
    corrupt = ImportResidueTag(
        run_id=BASE_TAG.run_id,
        source_project_name=BASE_TAG.source_project_name,
        timestamp=BASE_TAG.timestamp,
        merge_b64=schema_bad_b64,
    )
    assert corrupt.decode_merge_log() is None
