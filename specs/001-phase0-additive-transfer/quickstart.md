# Quickstart: Phase 0 — Additive Grammar Transfer

**Plan**: [plan.md](plan.md)
**Spec**: [spec.md](spec.md)

This guide walks an implementer or QA reviewer through validating that the Phase 0
module works end-to-end. It does **not** contain implementation code — that belongs
in `tasks.md` and the implementation phase.

## Prerequisites

- A working FlexTools installation that can host Python modules.
- flexlibs1 and the LibLCM .NET bridge available to FlexTools (the constitution's
  Principle II runtime stack).
- PyQt available to the FlexTools Python environment.
- The `tests/fixtures/toy_source/` and `tests/fixtures/empty_target/` FLEx project
  copies (these will be created during implementation; not committed here).
- The `gramtrans` package installed into the FlexTools modules directory per the
  host's convention (see research.md R3 for the entry-point shape).

## Setup

1. Open `tests/fixtures/toy_source/` in FlexTools. This is the source per
   Clarification Q2 (the host's open project).
2. Verify that the GramTrans module appears in FlexTools' module list.
3. Make a fresh copy of `tests/fixtures/empty_target/` to use as the target for this
   run. (Each scenario below assumes a fresh empty target so writes don't pollute
   the fixture.)
4. Take a snapshot of the target's pre-run state (object count per class, GUID list
   if helpful). Required for SC-004 verification.

## Scenario A — Full transfer (validates User Story 1, SC-001, SC-002, SC-003)

1. Launch GramTrans from the FlexTools module list.
2. **Confirm:** the main window shows "Source: ToySource" (the host's open project).
3. In the target picker, select the fresh copy of `empty_target/`. Confirm Run is
   still disabled (no Selection yet).
4. Toggle on all grammar piece categories.
5. Leave the "Include dependency closure" toggle ON (default per FR-013).
6. Click **Preview**.
7. **Confirm:** the WS mapping dialog appears (FR-011 / Q3). Map every listed source
   WS (both vernacular and analysis) to the corresponding target WS, creating any
   that don't yet exist. Confirm.
8. **Confirm:** the stats panel shows the planned counts per category. Note the
   "would add" totals. Confirm `identity_remap` is empty (or matches R6
   expectations).
9. Click **Move**.
10. **Confirm:** the stats panel updates to Move Mode counts. Wall-clock < 5 minutes
    for a ≤100-piece source (SC-001).
11. **Confirm:** all `added` counts equal the prior "would add" counts (SC-002 — no
    silent loss).
12. Open the target in FLEx (after Move completes). Verify:
    - Newly added objects exist with source GUIDs preserved (R6).
    - Each object's Import Residue field contains a tag of the form
      `GT|GT-YYYYMMDD-HHMMSS|ToySource|<iso-timestamp>` (E5 / Q5).
    - No GOLD object was modified (FR-022).
    - Every cross-reference resolves (SC-003 — zero dangling refs).
13. Compare the target's pre-run snapshot against post-run state for objects that
    *should not* have changed. Diff = exactly the added items (SC-004).

## Scenario B — Affix-only with closure pull-in (validates US3, FR-005, FR-007/Q4)

1. Launch with a fresh `empty_target/` copy.
2. Toggle ON only "Affixes". Leave closure toggle ON.
3. Open the affix tree picker. **Confirm:** tree shows `Template → Slot → Affix`
   hierarchy, with an "Unbound" branch at the top level (Q4).
4. Select one specific affix that references at least one inflection feature and
   one inflection class.
5. Click **Preview** → complete WS mapping → review counts.
6. **Confirm:** the stats panel shows:
   - Affixes: 1 added
   - Inflection Features: ≥1 added (closure pulled in)
   - Inflection Classes: ≥1 added (closure pulled in)
   - Allomorphs / APRs visible as pulled-in counts if the affix has them
7. Click **Move**. Verify the same closure objects exist in the target with
   resolved cross-references.

## Scenario C — Preview produces no writes (validates SC-006, Principle III)

1. Launch with a fresh `empty_target/` copy.
2. Take a target snapshot.
3. Select any category, complete WS mapping, click **Preview** only — do NOT click
   Move.
4. Close the module.
5. Take a post-Preview target snapshot.
6. **Confirm:** snapshots are byte-identical. SC-006 verified.

## Scenario D — Refuse same source and target (validates FR-019, Edge Case)

1. Launch GramTrans against `toy_source/`.
2. In the target picker, attempt to select `toy_source/` itself.
3. **Confirm:** the module refuses with a clear error and does not advance to the
   main run flow. No write occurred.

## Scenario E — Refuse incomplete WS mapping (validates FR-011 / Q3)

1. Launch with a fresh `empty_target/` copy.
2. Select any category whose items reference more than one WS.
3. Click **Preview**.
4. In the WS mapping dialog, leave at least one source WS unmapped. Try to confirm.
5. **Confirm:** the dialog refuses to close and re-highlights the unmapped row.

## Scenario F — Skip on unresolved closure with closure-off (validates FR-013)

1. Launch with a fresh `empty_target/` copy.
2. Toggle ON only "Affixes". Toggle OFF the closure toggle.
3. Select an affix whose dependencies (inflection feature, class) are not also
   selected directly.
4. Click **Preview**.
5. **Confirm:** the affix appears in `skips` with reason
   `BARE_BONES_MISSING_CLOSURE`. It is not "added" anywhere.
6. Cancel the run. Re-enable closure toggle. Re-preview.
7. **Confirm:** the affix now appears in `actions` with the feature/class pulled
   in.

## Acceptance for this phase

The phase is considered shipped when **all six scenarios above pass on the
fixture project pair**, AND the integration test suite snapshots match (see
[contracts/run-report.md](contracts/run-report.md) for the snapshot format).

Per constitution (Development Workflow), pre/post Import Residue artifacts MUST be
attached when shipping — the snapshot JSONs produced by Scenarios A and B are those
artifacts.
