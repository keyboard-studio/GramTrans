"""End-to-end workflow validation (live FLEx host required).

This module proves two things about the GramTrans export path:

1. test_persist_confirmation
   A full transfer (all categories except STEMS, Custom Fields ENABLED) writes
   objects that SURVIVE a fresh reopen of the target -- i.e. the writes really
   persisted through the PATH-CLOSE-REBIND custom-field branch of
   ``api.execute_move``. This is the #1 thing being validated.

2. test_full_selection_and_idempotency
   A first full run creates objects (actions > 0, no exceptions); a SECOND run
   over the same (un-restored) target produces ~0 new create actions -- the
   idempotency oracle. A normalized RunReport snapshot is compared against a
   golden JSON (written on first run, diffed thereafter).

SAFETY: The whole module SKIPS unless BOTH:
  - ``flexicon`` is importable, AND
  - the env flag ``GRAMTRANS_E2E=1`` is set.
So it never runs by accident (it restores and mutates a real project).

Run it:
    set GRAMTRANS_E2E=1 && set GRAMTRANS_DEBUG=1 && \
        pytest tests/integration/test_full_workflow_e2e.py -m integration -v

Prerequisites: FieldWorks 9 installed, source "Ejagham Mini" and target
"Ejagham Full GT-Test" present, target CLOSED in FLEx, a *.fwbackup in the repo
``backups/`` directory. See tests/integration/harness/README.md.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Module-level guards -- skip cleanly (never error) when prerequisites absent.
# ---------------------------------------------------------------------------

_FLEXICON_PRESENT = importlib.util.find_spec("flexicon") is not None
_E2E_ENABLED = os.environ.get("GRAMTRANS_E2E") == "1"

if not _FLEXICON_PRESENT:
    pytest.skip(
        "flexicon not importable; E2E workflow test needs a live FLEx host.",
        allow_module_level=True,
    )
if not _E2E_ENABLED:
    pytest.skip(
        "GRAMTRANS_E2E != 1; set it to opt into the destructive live E2E run.",
        allow_module_level=True,
    )

# Imports below are only reached when the guards pass (flexicon present).
# The harness lives alongside this file under ``harness/``; add this dir to
# sys.path (matching the repo convention of tests adding their own paths) so it
# imports as a top-level ``harness`` package without needing ``tests`` to be a
# package.
import sys  # noqa: E402

_THIS_DIR = str(Path(__file__).parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from harness import full_run, restore  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_NAME = "Ejagham Mini"
TARGET_NAME = "Ejagham Full GT-Test"
TARGET_PATH = r"C:\ProgramData\SIL\FieldWorks\Projects\Ejagham Full GT-Test"


def _summarize_actions_by_category(actions) -> str:
    """Group planned CREATE actions by GrammarCategory and (where present)
    match_via, so an idempotency failure shows exactly which categories
    re-planned creates on the second run.

    Returns a plain-ASCII multi-line report. Robust to actions missing
    ``category`` / ``match_via`` / ``summary`` attributes.
    """
    from collections import Counter

    by_cat: Counter = Counter()
    by_cat_match: Counter = Counter()
    examples: dict = {}
    for a in actions:
        cat = getattr(a, "category", None)
        cat_name = getattr(cat, "value", None) or str(cat)
        match_via = getattr(a, "match_via", None) or "-"
        by_cat[cat_name] += 1
        by_cat_match[(cat_name, match_via)] += 1
        if cat_name not in examples:
            examples[cat_name] = getattr(a, "summary", "") or ""

    lines = ["", "=== run #2 create actions by category ==="]
    for cat_name, n in by_cat.most_common():
        lines.append("  %-24s %5d   e.g. %s" % (cat_name, n, examples.get(cat_name, "")))
    lines.append("")
    lines.append("=== by (category, match_via) ===")
    for (cat_name, match_via), n in sorted(
        by_cat_match.items(), key=lambda kv: (-kv[1], kv[0])
    ):
        lines.append("  %-24s %-14s %5d" % (cat_name, match_via, n))
    lines.append("")
    lines.append("TOTAL create actions: %d" % len(actions))
    return "\n".join(lines)

_SNAPSHOT_DIR = Path(__file__).parent / "_snapshots"
_GOLDEN_PATH = _SNAPSHOT_DIR / "full_e2e_post.json"


# ---------------------------------------------------------------------------
# Snapshot normalization -- strip per-run volatile fields before golden diff.
# ---------------------------------------------------------------------------

def _normalize_snapshot(snapshot_json: str) -> dict:
    """Parse a RunReport snapshot and null out fields that vary per run.

    run_id / started_at / wall_clock_seconds are inherently volatile and would
    make every golden comparison fail; blank them so the diff is about the
    per-category / skips shape, which is what idempotency is really about.
    """
    data = json.loads(snapshot_json)
    ctx = data.get("context", {})
    ctx["run_id"] = "<normalized>"
    ctx["started_at"] = "<normalized>"
    data["wall_clock_seconds"] = 0.0
    return data


def _write_or_diff_golden(report) -> None:
    """Write the golden snapshot if absent, else diff and fail on drift."""
    normalized = _normalize_snapshot(report.to_snapshot_json())
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    if not _GOLDEN_PATH.exists():
        _GOLDEN_PATH.write_text(
            json.dumps(normalized, indent=2, sort_keys=False),
            encoding="utf-8",
        )
        print("[INFO] Wrote new golden snapshot: %s" % _GOLDEN_PATH)
        return

    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    assert normalized == golden, (
        "[FAIL] RunReport snapshot drifted from golden %s.\n"
        "Delete the golden to re-baseline if the change is intended.\n"
        "got:    %s\n"
        "golden: %s"
        % (
            _GOLDEN_PATH,
            json.dumps(normalized, indent=2, sort_keys=False),
            json.dumps(golden, indent=2, sort_keys=False),
        )
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_persist_confirmation():
    """Full transfer writes must survive a fresh reopen (persist through
    PATH-CLOSE-REBIND with Custom Fields enabled)."""
    # Baseline BEFORE any writes: restore clean, then count.
    try:
        backup = restore.newest_backup()
    except restore.RestoreError as exc:
        pytest.skip(str(exc))
    try:
        restore.restore_target(TARGET_NAME, backup_path=backup)
    except restore.RestoreError as exc:
        pytest.skip(str(exc))

    baseline = full_run.reopen_and_count(TARGET_NAME)
    assert baseline, (
        "[FAIL] Baseline inventory came back empty; no accessor resolved -- "
        "cannot prove persistence without at least one count."
    )

    # Run the full transfer (Custom Fields enabled via build_full_selection).
    plan, report = full_run.run_full_transfer(SOURCE_NAME, TARGET_NAME, TARGET_PATH)
    assert plan is not None and report is not None

    # Reopen fresh and prove the writes persisted (inventory grew).
    after = full_run.reopen_and_count(TARGET_NAME)
    assert after, "[FAIL] Post-run inventory came back empty."

    before_total = full_run.total_count(baseline)
    after_total = full_run.total_count(after)
    assert after_total > before_total, (
        "[FAIL] Inventory did not grow after a full transfer -- writes did not "
        "persist through reopen. baseline=%r after=%r" % (baseline, after)
    )


def test_full_selection_and_idempotency():
    """First run creates objects; a second run (no restore) creates ~0 new.

    See _summarize_actions_by_category (module scope) for the diagnostic dumped
    on failure.
    """
    try:
        backup = restore.newest_backup()
    except restore.RestoreError as exc:
        pytest.skip(str(exc))
    try:
        restore.restore_target(TARGET_NAME, backup_path=backup)
    except restore.RestoreError as exc:
        pytest.skip(str(exc))

    # Run #1 -- should create objects.
    plan1, report1 = full_run.run_full_transfer(SOURCE_NAME, TARGET_NAME, TARGET_PATH)
    assert len(plan1.actions) > 0, (
        "[FAIL] First full run planned zero actions; nothing to transfer?"
    )

    # Run #2 -- WITHOUT restore. Idempotency oracle: ~0 new create actions.
    plan2, report2 = full_run.run_full_transfer(SOURCE_NAME, TARGET_NAME, TARGET_PATH)
    if len(plan2.actions) != 0:
        breakdown = _summarize_actions_by_category(plan2.actions)
        # Persist a full breakdown next to the snapshots so the terminal
        # truncation doesn't hide which categories are non-idempotent.
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        out = _SNAPSHOT_DIR / "idempotency_run2_breakdown.txt"
        out.write_text(breakdown, encoding="utf-8")
        pytest.fail(
            "[FAIL] Second run planned %d create actions; expected 0 (idempotency).\n"
            "Per-category breakdown (full copy written to %s):\n%s"
            % (len(plan2.actions), out, breakdown)
        )

    # Emit / diff the golden snapshot from the second (steady-state) run.
    _write_or_diff_golden(report2)
