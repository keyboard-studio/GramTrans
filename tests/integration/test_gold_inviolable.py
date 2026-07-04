"""T035: FR-022 GOLD inviolability — integration scaffold against Ejagham Mini -> Ejagham Full GT-Test."""
from __future__ import annotations

import pytest

# All integration tests are marked so unit-only runs skip them:
#   pytest -m 'not integration'
# The marker is registered in pyproject.toml.
pytestmark = pytest.mark.integration


def test_gold_objects_byte_identical_before_and_after_move() -> None:
    """FR-022: every GOLD object in the target shows zero modifications byte-for-byte after Move.

    Requires:
    - FlexTools host running this test (not raw pytest from CLI).
    - Ejagham Mini at C:\\ProgramData\\SIL\\FieldWorks\\Projects\\Ejagham Mini
    - Ejagham Full GT-Test freshly restored from backups/Ejagham Full.fwbackup
      (the restored target must contain at least some GOLD objects so the test
      is non-vacuous; confirm via FLEx Grammar > Gram. Categories before running)

    Asserts: a pre-run snapshot of all GOLD-tagged objects in the target
    (serialised field-by-field) is compared byte-for-byte against a post-run
    snapshot taken immediately after execute_move() returns.  Any difference —
    including Description field appends, GUID field changes, or LiftResidue
    mutations — is a FR-022 violation.  The module must detect GOLD status
    during preview and emit a Skip(reason=GOLD_VIOLATION) rather than writing.

    GOLD = objects in the LangProject.PartsOfSpeech hierarchy that carry the
    'gold' annotation per the GOLD Community of Practice ontology import.
    Identification method: flexicon object attribute or Description field
    containing the GOLD marker string (per research.md R8).
    """
    pytest.skip(
        "Integration test — requires FlexTools host. "
        "Run via FlexTools MCP `flextools_run_module` or under the host directly."
    )

    if False:
        from gramtrans.Lib.api import (  # noqa: F401
            bind_target,
            compute_preview,
            execute_move,
            initialize_run,
        )
        from gramtrans.Lib.models import GrammarCategory  # noqa: F401

        ctx = initialize_run(source_project_name="Ejagham Mini")
        bind_target(ctx, target_name="Ejagham Full GT-Test")

        # Snapshot only GOLD objects before the run.
        pre_gold_snapshot: dict = ctx.target_project.snapshot_gold_objects()

        # Non-vacuous guard: the test is meaningless if there are no GOLD objects.
        assert pre_gold_snapshot, (
            "FR-022: no GOLD objects found in target — restore a target that "
            "contains GOLD ontology imports before running this test."
        )

        preview_result = compute_preview(ctx, categories=list(GrammarCategory), include_closure=True)
        execute_move(ctx, plan=preview_result.plan)

        post_gold_snapshot: dict = ctx.target_project.snapshot_gold_objects()

        for guid, pre_repr in pre_gold_snapshot.items():
            assert guid in post_gold_snapshot, (
                f"FR-022: GOLD object {guid} vanished after Move"
            )
            assert post_gold_snapshot[guid] == pre_repr, (
                f"FR-022 violated: GOLD object {guid} was modified during Move.\n"
                f"  before: {pre_repr!r}\n"
                f"  after:  {post_gold_snapshot[guid]!r}"
            )
