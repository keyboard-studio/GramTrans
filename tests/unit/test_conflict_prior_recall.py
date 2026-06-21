"""T045 -- load_prior_log / load_prior_decision tests (US3 recall).

Spec: research.md R7 (FR-207 / FR-215 graceful degradation).
"""
from __future__ import annotations

from gramtrans.Lib.conflict import (
    detect_conflicts,
    load_prior_decision,
    load_prior_log,
)
from gramtrans.Lib.models import (
    MergeDecision,
    MergeDecisionLog,
    MergeResolution,
)
from gramtrans.Lib.residue import ImportResidueTag


GUID = "15a59768-ad27-4e12-bf9f-719c55854c9f"

PRIOR_TAG = ImportResidueTag(
    run_id="GT-20260101-120000",
    source_project_name="Ejagham Mini",
    timestamp="2026-01-01T12:00:00",
)


def _make_target(lift_residue):
    """Tiny LCM-shaped fake exposing a LiftResidue attribute."""
    class _T:
        pass
    t = _T()
    t.LiftResidue = lift_residue
    return t


def _serialized_with_log(decisions):
    log = MergeDecisionLog(target_guid=GUID, decisions=decisions)
    return PRIOR_TAG.with_snapshot({"k": "v"}).with_merge_log(log).serialize(), log


# ============================================================================
# Happy paths
# ============================================================================

def test_load_prior_log_returns_decoded_log():
    serialized, expected = _serialized_with_log((
        MergeDecision(
            field_name="Comment",
            resolution=MergeResolution.TAKE_SOURCE,
            left_value="old",
            right_value="new",
        ),
    ))
    tgt = _make_target(serialized)
    log = load_prior_log(tgt)
    assert log is not None
    assert log == expected


def test_load_prior_decision_finds_matching_field():
    serialized, _ = _serialized_with_log((
        MergeDecision(field_name="A", resolution=MergeResolution.TAKE_SOURCE),
        MergeDecision(field_name="B", resolution=MergeResolution.SKIP),
    ))
    tgt = _make_target(serialized)
    d = load_prior_decision(tgt, "B")
    assert d is not None
    assert d.resolution == MergeResolution.SKIP


def test_load_prior_decision_returns_none_for_unmatched_field():
    serialized, _ = _serialized_with_log((
        MergeDecision(field_name="OtherField", resolution=MergeResolution.TAKE_SOURCE),
    ))
    tgt = _make_target(serialized)
    assert load_prior_decision(tgt, "Comment") is None


# ============================================================================
# Graceful degradation (FR-215)
# ============================================================================

def test_load_prior_log_returns_none_when_no_residue():
    tgt = _make_target(None)
    assert load_prior_log(tgt) is None


def test_load_prior_log_returns_none_for_empty_string():
    tgt = _make_target("")
    assert load_prior_log(tgt) is None


def test_load_prior_log_returns_none_for_corrupted_tag():
    tgt = _make_target("not a valid tag string")
    assert load_prior_log(tgt) is None


def test_load_prior_log_returns_none_when_tag_has_no_merge_segment():
    """A snap=-only tag (Phase 1) carries no MergeDecisionLog."""
    serialized = PRIOR_TAG.with_snapshot({"k": "v"}).serialize()
    tgt = _make_target(serialized)
    assert load_prior_log(tgt) is None


def test_load_prior_decision_returns_none_on_corrupted_tag():
    tgt = _make_target("not a tag")
    assert load_prior_decision(tgt, "Comment") is None


def test_load_prior_log_handles_object_without_lift_residue():
    class _NoAttr:
        pass
    assert load_prior_log(_NoAttr()) is None


def test_load_prior_log_handles_none_object():
    assert load_prior_log(None) is None


# ============================================================================
# Integration with detect_conflicts -- the recall threading path
# ============================================================================

def test_detect_conflicts_threads_prior_log_into_prompts():
    """The end-to-end recall flow: prior log threaded through
    detect_conflicts surfaces as prompt.prior_decision."""
    prior_log = MergeDecisionLog(
        target_guid=GUID,
        decisions=(
            MergeDecision(
                field_name="Comment",
                resolution=MergeResolution.MERGE,
                left_value="old",
                right_value="new",
                prior_run_id="GT-20260101-120000",
            ),
        ),
    )
    src = {"Comment": "src"}
    tgt = {"Comment": "tgt"}
    prompts = detect_conflicts(src, tgt, GUID, "LexEntry", prior_log=prior_log)
    assert len(prompts) == 1
    assert prompts[0].prior_decision is not None
    assert prompts[0].prior_decision.resolution == MergeResolution.MERGE
    assert prompts[0].prior_decision.prior_run_id == "GT-20260101-120000"


def test_full_recall_path_load_then_detect():
    """Realistic flow: read the target's residue, recover the log, feed
    it into detect_conflicts -- prompts carry the prior decisions."""
    serialized, _ = _serialized_with_log((
        MergeDecision(
            field_name="Comment",
            resolution=MergeResolution.KEEP_TARGET,
            prior_run_id="GT-20260101-120000",
        ),
    ))
    tgt_obj = _make_target(serialized)
    log = load_prior_log(tgt_obj)
    assert log is not None

    src = {"Comment": "src"}
    tgt = {"Comment": "tgt"}
    prompts = detect_conflicts(src, tgt, GUID, "LexEntry", prior_log=log)
    assert prompts[0].prior_decision.resolution == MergeResolution.KEEP_TARGET
