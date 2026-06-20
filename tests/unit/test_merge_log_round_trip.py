"""T015 — MergeDecisionLog JSON round-trip and validation tests.

Spec: data-model.md E11 / E12.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.models import (
    MergeDecision,
    MergeDecisionLog,
    MergeResolution,
)


def test_decision_log_round_trip_empty():
    log = MergeDecisionLog(target_guid="abc", decisions=())
    s = log.to_json()
    assert MergeDecisionLog.from_json(s) == log


def test_decision_log_round_trip_single():
    log = MergeDecisionLog(
        target_guid="abc-123",
        decisions=(
            MergeDecision(
                field_name="Comment",
                resolution=MergeResolution.TAKE_SOURCE,
                left_value="old",
                right_value="new",
            ),
        ),
    )
    parsed = MergeDecisionLog.from_json(log.to_json())
    assert parsed == log


def test_decision_log_round_trip_all_resolutions():
    log = MergeDecisionLog(
        target_guid="abc-123",
        decisions=(
            MergeDecision(field_name="A", resolution=MergeResolution.TAKE_SOURCE),
            MergeDecision(field_name="B", resolution=MergeResolution.KEEP_TARGET),
            MergeDecision(
                field_name="C", resolution=MergeResolution.MERGE,
                left_value=1, right_value=2,
            ),
            MergeDecision(field_name="D", resolution=MergeResolution.SKIP),
            MergeDecision(
                field_name="E", resolution=MergeResolution.EDIT_CUSTOM,
                custom_value="user-typed",
            ),
        ),
    )
    parsed = MergeDecisionLog.from_json(log.to_json())
    assert parsed == log


def test_decision_log_round_trip_with_prior_run_id():
    log = MergeDecisionLog(
        target_guid="abc",
        decisions=(
            MergeDecision(
                field_name="A",
                resolution=MergeResolution.TAKE_SOURCE,
                prior_run_id="GT-20260101-120000",
            ),
        ),
    )
    parsed = MergeDecisionLog.from_json(log.to_json())
    assert parsed.decisions[0].prior_run_id == "GT-20260101-120000"


def test_decision_log_rejects_duplicate_field_names():
    with pytest.raises(ValueError, match="duplicate"):
        MergeDecisionLog(
            target_guid="abc",
            decisions=(
                MergeDecision(field_name="X", resolution=MergeResolution.TAKE_SOURCE),
                MergeDecision(field_name="X", resolution=MergeResolution.KEEP_TARGET),
            ),
        )


def test_decision_requires_field_name():
    with pytest.raises(ValueError, match="field_name"):
        MergeDecision(field_name="", resolution=MergeResolution.TAKE_SOURCE)


def test_decision_edit_custom_requires_custom_value():
    with pytest.raises(ValueError, match="EDIT_CUSTOM"):
        MergeDecision(
            field_name="X",
            resolution=MergeResolution.EDIT_CUSTOM,
            # custom_value not provided
        )


def test_decision_non_custom_rejects_custom_value():
    with pytest.raises(ValueError, match="custom_value"):
        MergeDecision(
            field_name="X",
            resolution=MergeResolution.TAKE_SOURCE,
            custom_value="should_not_be_here",
        )


def test_to_json_is_deterministic_sort_keys():
    """Same input -> same JSON string, regardless of decision tuple order
    being stable (so disk diffs are meaningful)."""
    log_a = MergeDecisionLog(
        target_guid="abc",
        decisions=(
            MergeDecision(field_name="A", resolution=MergeResolution.TAKE_SOURCE),
            MergeDecision(field_name="B", resolution=MergeResolution.KEEP_TARGET),
        ),
    )
    log_b = MergeDecisionLog(
        target_guid="abc",
        decisions=(
            MergeDecision(field_name="A", resolution=MergeResolution.TAKE_SOURCE),
            MergeDecision(field_name="B", resolution=MergeResolution.KEEP_TARGET),
        ),
    )
    assert log_a.to_json() == log_b.to_json()
