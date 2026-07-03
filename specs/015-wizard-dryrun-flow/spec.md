# Feature Specification: Wizard Flow — Drop the Preview Step, Dry-Run on Finish

**Feature Branch**: `015-wizard-dryrun-flow`

**Created**: 2026-07-03

**Status**: Draft

**Input**: User description: "Remove the standalone Preview step and gate Move behind a dry run on the Finish page — feature 015. Fifth of five features chunked from the per-item merge-preview + SIMILAR-resolution plan."

## Context

With per-item merge previews now docked on every selection page (feature 014), the wizard's
dedicated **Preview step** (old Step 6) is redundant — the user has already seen, item by item,
what each transfer will do. This feature collapses the seven-page flow to six by removing that
standalone step and folding its plan-assembly + report into a **dry-run on the Finish page**:
the user clicks "Dry run" to compute the plan and see the aggregate report, and only then is
"Move" enabled.

It is the fifth and final chunk (011 → 012 → 013 → 014 → **015 flow**). It is a pure
wizard-flow / interaction change in `Lib/ui/selection_wizard.py`: no engine change, no new diff
logic. Its correctness hinges on preserving the existing plan-assembly and staleness guarantees
while relocating them.

Key behaviors from the source plan (section 5):

- **The `_PagePreview` object is retained for back-compat but no longer added as a page.** The
  "Step N of 7" titles renumber to "of 6"; Finish becomes "Step 6 of 6". The `page_preview()`
  accessor keeps returning the retained instance so page-order tests keep passing.
- **The plan-assembly body is extracted** from `_PagePreview._on_preview` into a module-level
  `_compute_wizard_plan(wizard)` that performs the identical selection assembly (affix picks +
  phonology collapse + Layer-1 conflict modes + WS mapping) **plus** copying the pages'
  `similar_resolutions` onto the selection (via `dataclasses.replace`) before building the plan
  and report. `_PagePreview._on_preview` becomes a thin wrapper (still callable for back-compat).
- **Move requires a dry run first.** The Finish page adds a "Dry run (preview plan)" button;
  Move starts disabled and enables only after a successful dry run (caching the fresh plan).
  Re-entering Finish, and any post-move invalidation, clears the cached plan so Move re-requires
  a dry run. This preserves the old `isComplete` freshness gating and pairs with the engine's
  `PreviewStale` backstop.

Grounded in the source plan's cited lines: the `_PagePreview._on_preview` body and its cached
plan, the seven "Step N of 7" title sites, the `_PageFinish` Move handler and post-move
invalidation, the `page_preview()` accessor, and the wizard page-order / page-flow tests.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A six-page flow with no standalone Preview step (Priority: P1)

The wizard presents six pages — Project+WS, Phonology, Affixes, Skeleton, Grammatical deps,
Finish — with step titles numbered "of 6"; there is no separate Preview page, because per-item
previews now live on the selection pages.

**Why this priority**: The flow reduction is the visible outcome and the reason the feature
exists; it must be correct and not break page ordering or accessors other code depends on.

**Independent Test**: Construct the wizard and assert six pages in the specified order, "Step N
of 6" titles, no Preview page, and that `page_preview()` still returns a (non-added) instance.

**Acceptance Scenarios**:

1. **Given** the wizard is constructed, **When** its pages are enumerated, **Then** there are
   six pages in the order Project+WS → Phonology → Affixes → Skeleton → Grammatical deps →
   Finish, and no standalone Preview page is present.
2. **Given** the wizard, **When** step titles are read, **Then** every page reads "Step N of 6"
   and Finish reads "Step 6 of 6".
3. **Given** the wizard, **When** `page_preview()` is called, **Then** it returns the retained
   `_PagePreview` instance (back-compat) even though it is not an added page.

---

### User Story 2 - Dry run on Finish computes the plan and report (Priority: P1)

On the Finish page, clicking "Dry run" assembles the transfer plan from all page selections —
including each page's SIMILAR resolutions — and shows the aggregate report in the existing stats
panel, identically to what the old Preview step produced.

**Why this priority**: The dry run is where the plan is now built and shown; it must reproduce
the old preview's assembly exactly (including the new resolutions) or transfers will diverge from
what the user reviewed.

**Independent Test**: Drive the wizard to Finish with fabricated selections including a SIMILAR
resolution; click Dry run; assert the computed plan matches `_compute_wizard_plan`'s output and
that the resolution is present on the assembled selection.

**Acceptance Scenarios**:

1. **Given** the Finish page, **When** Dry run is clicked, **Then** the plan is assembled via the
   shared `_compute_wizard_plan` (affix picks + phonology collapse + Layer-1 modes + WS mapping +
   `similar_resolutions` copied across) and the report is shown in the stats panel.
2. **Given** pages carrying SIMILAR resolutions, **When** the dry run runs, **Then** the
   assembled selection carries those resolutions (not dropped by reconstruction).
3. **Given** the old `_PagePreview._on_preview`, **When** it is called (back-compat), **Then** it
   delegates to the shared `_compute_wizard_plan` and returns the same plan/report.

---

### User Story 3 - Move is gated behind a fresh dry run (Priority: P1)

The Move button is disabled until a dry run has produced a plan; Move then uses that cached plan.
Changing selections and returning to Finish, or completing a Move, clears the cached plan so a
fresh dry run is required before Move can run again.

**Why this priority**: Preserves the old freshness guarantee (Move never runs a stale plan) now
that the dedicated preview page is gone; a stale-plan Move would transfer something the user
never reviewed.

**Independent Test**: At Finish, assert Move is disabled; run a dry run and assert Move enables
and uses the cached plan; re-enter Finish and assert Move is disabled again pending a new dry run.

**Acceptance Scenarios**:

1. **Given** the Finish page is first shown, **When** no dry run has run, **Then** Move is
   disabled.
2. **Given** a successful dry run, **When** it completes, **Then** Move is enabled and, when
   clicked, uses the cached plan (not a re-derived one).
3. **Given** a cached plan, **When** the user changes selections and returns to Finish, **Then**
   the cached plan is cleared and Move is disabled until a new dry run.
4. **Given** a completed Move, **When** post-move invalidation runs, **Then** the cached plan is
   cleared (consistent with the old invalidation) and the `PreviewStale` engine backstop remains
   in force.

---

### Edge Cases

- **User edits a selection page after a dry run, then navigates straight to Finish**: the cached
  plan is cleared on Finish initialize, so Move is disabled until re-running the dry run.
- **Dry run produces lossy/excluded warnings** (e.g. phonology deselections): they surface in the
  report exactly as the old preview surfaced them (fed into the same aggregated Move gate).
- **`_PagePreview` consulted by legacy code/tests**: `page_preview()` still returns the retained
  instance; nothing that reads it breaks even though it is not a page.
- **A dry run fails to assemble a plan**: Move stays disabled (no cached plan), no partial state.
- **Re-running the dry run**: recomputes and refreshes the cached plan/report (idempotent from
  the user's view).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The wizard MUST construct but NOT add the `_PagePreview` page, yielding a six-page
  flow: Project+WS → Phonology → Affixes → Skeleton → Grammatical deps → Finish.
- **FR-002**: All "Step N of 7" titles MUST be renumbered to "of 6"; the Finish page MUST read
  "Step 6 of 6".
- **FR-003**: The `page_preview()` accessor MUST continue to return the retained `_PagePreview`
  instance for back-compat, so page-order tests and any legacy readers keep working.
- **FR-004**: The plan-assembly body MUST be extracted into a module-level
  `_compute_wizard_plan(wizard) -> (plan, report)` performing the identical selection assembly
  (affix picks + phonology collapse + Layer-1 conflict modes + WS mapping) PLUS copying the
  pages' `similar_resolutions` onto the selection via `dataclasses.replace`, then building the
  plan and the run report (including any excluded-lossy warnings).
- **FR-005**: `_PagePreview._on_preview` MUST become a thin wrapper delegating to
  `_compute_wizard_plan` (behavior-preserving for any remaining caller).
- **FR-006**: The Finish page MUST add a "Dry run (preview plan)" control that calls
  `_compute_wizard_plan`, caches the resulting plan, shows the report in the existing stats
  panel, and enables Move.
- **FR-007**: The Move button MUST start disabled and become enabled only after a successful dry
  run; Move MUST use the cached plan rather than re-deriving one.
- **FR-008**: The cached plan MUST be cleared on Finish-page initialize (so returning after
  changing picks forces a fresh dry run) and on post-move invalidation (replacing the old
  invalidation), keeping the `PreviewStale` engine backstop in force.
- **FR-009**: This feature MUST NOT change transfer engine behavior, diff logic, or the per-item
  pane; it only relocates plan assembly and gates Move. It depends on feature 014 (the pane and
  the pages' `similar_resolutions` store the dry run reads).

### Key Entities *(include if feature involves data)*

- **`_compute_wizard_plan`**: the extracted module-level assembler producing `(plan, report)`
  from all page selections, including copied-across `similar_resolutions`.
- **Cached plan (Finish page)**: the plan produced by the most recent dry run; the gate for Move;
  cleared on Finish initialize and post-move.
- **Retained `_PagePreview`**: the no-longer-added preview object kept for accessor/back-compat.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The wizard presents exactly six pages in the specified order with no standalone
  Preview page, and every step title reads "of 6".
- **SC-002**: A dry run on Finish produces a plan and report identical to what the old Preview
  step produced for the same selections (including `similar_resolutions` present on the assembled
  selection).
- **SC-003**: Move is disabled with no dry run, enabled after a successful dry run, uses the
  cached plan, and returns to disabled after re-entering Finish or completing a Move.
- **SC-004**: `page_preview()` returns a non-None retained instance and the page-order test suite
  passes unchanged; the page-flow test suite passes updated for six pages + dry-run gating.
- **SC-005**: `similar_resolutions` are preserved through assembly in 100% of dry runs (0 dropped
  by reconstruction), so the moved transfer matches the reviewed selection.

## Assumptions

- Feature 014 is merged: each selection page exposes its `similar_resolutions` store, and the
  per-item preview lives on the selection pages (making the standalone Preview step redundant).
- The `similar_resolutions` copied across here are action-agnostic: this feature preserves the
  map verbatim (via `dataclasses.replace`) whether an entry's action is `overwrite`, `merge`, or
  `create_new` (the three-way vocabulary from 011). No assembler logic depends on the action; the
  planner/executor (013) interpret it.
- The transfer engine, `PreviewStale` staleness detection, and the aggregated confirm-on-Move
  gate are unchanged; this feature reuses them and only relocates when/where the plan is built and
  gated.
- "Move requires a dry run first" is the resolved design decision (guarantees plan freshness and
  matches the old `isComplete` gating); an always-enabled Move that silently derives a plan is
  explicitly rejected.
- **012's preview cache key is a 4-tuple `(category, source_guid, target_guid, mode)`** (012
  FR-011, fixed in cycle-1 review). Any dry-run / Finish-page code that touches the 012 service
  MUST honor the 4-tuple key; a resolution-action change is reflected by the differing `mode`, not
  by cache invalidation. This is orthogonal to the wizard's own cached *plan* invalidation.
- The existing stats panel already renders the run report (including identity remap from 013);
  the dry run feeds it the same report object.
- Page-order back-compat (`page_preview()` + `test_wizard_page_order.py`) is a hard constraint;
  the `_PagePreview` instance is retained purely to satisfy it.
- This is the final chunk; after it, the per-item merge-preview + SIMILAR-resolution workflow is
  complete end to end (data model → diff engine → transfer → pane → flow).
