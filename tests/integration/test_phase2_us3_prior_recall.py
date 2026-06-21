"""T046 -- Phase 2 / US3 integration: prior-run decision recall.

Scenario C from quickstart.md: run a transfer once (capturing the user's
choices into the residue tag's merge= segment), then re-run with no
source-side changes -- the prompts pre-fill with the prior decisions
and accepting all yields a no-op confirmation.

This integration test exercises the data path without involving a real
LCM target.  The residue tag round-trip is the test surface.
"""
from __future__ import annotations

from gramtrans.Lib.conflict import (
    build_session_from_resolutions,
    detect_conflicts,
    load_prior_log,
)
from gramtrans.Lib.models import (
    MergeDecision,
    MergeDecisionLog,
    MergeResolution,
)
from gramtrans.Lib.residue import ImportResidueTag


GUID = "15a59768-ad27-4e12-bf9f-719c55854c9f"
RUN1_ID = "GT-20260601-100000"
RUN2_ID = "GT-20260620-200000"

RUN1_TAG = ImportResidueTag(
    run_id=RUN1_ID, source_project_name="Ejagham Mini", timestamp="2026-06-01T10:00:00",
)
RUN2_TAG = ImportResidueTag(
    run_id=RUN2_ID, source_project_name="Ejagham Mini", timestamp="2026-06-20T20:00:00",
)


class _FakeTarget:
    """Stand-in for an LCM object exposing a LiftResidue attribute that
    persists across reads -- mimics flexlibs2 setattr-on-None behaviour
    from Phase 1.3c."""

    LiftResidue = None


def test_us3_full_recall_path():
    # ---- Run 1: user picks MERGE on a Comment conflict ----
    src_props = {"Comment": "src-value"}
    tgt_pre_props = {"Comment": "tgt-original"}

    run1_prompts = detect_conflicts(src_props, tgt_pre_props, GUID, "LexEntry")
    assert run1_prompts[0].prior_decision is None  # first run -- no recall

    run1_decisions = (
        MergeDecision(
            field_name="Comment",
            resolution=MergeResolution.MERGE,
            left_value="tgt-original",
            right_value="src-value",
        ),
    )
    run1_session = build_session_from_resolutions(run1_prompts, run1_decisions)
    run1_log = run1_session.merge_decisions_by_guid[GUID]

    # Simulate: transfer.execute stamps the residue tag with the merge log.
    tgt = _FakeTarget()
    tagged = RUN1_TAG.with_snapshot(tgt_pre_props).with_merge_log(run1_log)
    tgt.LiftResidue = tagged.serialize()

    # ---- Run 2 (a week later): same source/target, recall the log ----
    recalled_log = load_prior_log(tgt)
    assert recalled_log == run1_log

    run2_prompts = detect_conflicts(src_props, tgt_pre_props, GUID, "LexEntry", prior_log=recalled_log)
    assert len(run2_prompts) == 1
    assert run2_prompts[0].prior_decision is not None
    assert run2_prompts[0].prior_decision.resolution == MergeResolution.MERGE


def test_us3_accept_all_prior_decisions_yields_same_log():
    """If the user accepts every pre-filled prior decision, the next
    log is structurally identical (same field names, same resolutions)."""
    src_props = {"A": "x", "B": "y"}
    tgt_pre_props = {"A": "x-old", "B": "y-old"}

    prior_log = MergeDecisionLog(
        target_guid=GUID,
        decisions=(
            MergeDecision(field_name="A", resolution=MergeResolution.TAKE_SOURCE, prior_run_id=RUN1_ID),
            MergeDecision(field_name="B", resolution=MergeResolution.KEEP_TARGET, prior_run_id=RUN1_ID),
        ),
    )

    prompts = detect_conflicts(src_props, tgt_pre_props, GUID, "LexEntry", prior_log=prior_log)
    # User accepts each pre-filled prior decision: returned decisions
    # echo the prior_decision payload (resolution + prior_run_id).
    accepted = tuple(
        MergeDecision(
            field_name=p.field_name,
            resolution=p.prior_decision.resolution,
            prior_run_id=p.prior_decision.prior_run_id,
        )
        for p in prompts
    )
    session = build_session_from_resolutions(prompts, accepted)
    log2 = session.merge_decisions_by_guid[GUID]
    # Same field names, same resolutions, same prior_run_ids
    assert {d.field_name for d in log2.decisions} == {"A", "B"}
    assert all(d.prior_run_id == RUN1_ID for d in log2.decisions)


def test_us3_user_overrides_prior_decision():
    """If the user changes their mind on one field, the new MergeDecision
    drops the prior_run_id (marking it a fresh resolution)."""
    src_props = {"Comment": "src"}
    tgt_pre_props = {"Comment": "tgt"}
    prior_log = MergeDecisionLog(
        target_guid=GUID,
        decisions=(
            MergeDecision(field_name="Comment", resolution=MergeResolution.MERGE, prior_run_id=RUN1_ID),
        ),
    )
    prompts = detect_conflicts(src_props, tgt_pre_props, GUID, "LexEntry", prior_log=prior_log)
    # User overrides: chooses KEEP_TARGET this run.  prior_run_id NOT set.
    overridden = (
        MergeDecision(field_name="Comment", resolution=MergeResolution.KEEP_TARGET),
    )
    session = build_session_from_resolutions(prompts, overridden)
    new_decision = session.merge_decisions_by_guid[GUID].decisions[0]
    assert new_decision.resolution == MergeResolution.KEEP_TARGET
    assert new_decision.prior_run_id == ""  # fresh decision, not carried over


def test_us3_corrupted_residue_falls_back_to_fresh_prompt():
    """FR-215 -- a corrupted residue tag returns None from load_prior_log;
    detect_conflicts then sees prior_log=None and surfaces a fresh prompt."""
    tgt = _FakeTarget()
    tgt.LiftResidue = "GT|corrupted|tag|format|whatever"
    log = load_prior_log(tgt)
    assert log is None

    src_props = {"Comment": "src"}
    tgt_pre_props = {"Comment": "tgt"}
    prompts = detect_conflicts(src_props, tgt_pre_props, GUID, "LexEntry", prior_log=log)
    assert prompts[0].prior_decision is None  # fresh prompt -- no recall


def test_us3_run2_residue_carries_new_run_id_in_outer_tag():
    """The outer ImportResidueTag's run_id updates on each run, but the
    per-decision prior_run_id traces back to the original run that
    answered the field."""
    # Run 1 writes its decisions
    log1 = MergeDecisionLog(
        target_guid=GUID,
        decisions=(
            MergeDecision(field_name="C", resolution=MergeResolution.MERGE, prior_run_id=""),
        ),
    )
    tag1 = RUN1_TAG.with_snapshot({}).with_merge_log(log1)
    s1 = tag1.serialize()
    parsed1 = ImportResidueTag.parse(s1)
    assert parsed1.run_id == RUN1_ID

    # Run 2 carries forward: parse run1 residue, build log2 with prior_run_id=RUN1
    log2 = MergeDecisionLog(
        target_guid=GUID,
        decisions=(
            MergeDecision(field_name="C", resolution=MergeResolution.MERGE, prior_run_id=RUN1_ID),
        ),
    )
    tag2 = RUN2_TAG.with_snapshot({}).with_merge_log(log2)
    parsed2 = ImportResidueTag.parse(tag2.serialize())
    # Outer tag's run_id reflects run 2; the inner decision attributes
    # the field-level resolution to run 1.
    assert parsed2.run_id == RUN2_ID
    inner_decisions = parsed2.decode_merge_log().decisions
    assert inner_decisions[0].prior_run_id == RUN1_ID
