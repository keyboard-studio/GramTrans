# Feature Specification: SIMILAR Resolution in the Transfer Pipeline

**Feature Branch**: `013-similar-resolution-transfer`

**Created**: 2026-07-03

**Status**: Draft

**Input**: User description: "Thread SIMILAR resolutions through the transfer planner and executor — feature 013. Third of five features chunked from the per-item merge-preview + SIMILAR-resolution plan."

## Context

Feature 011 put a per-item `SimilarResolution` (overwrite / merge into a target GUID, or
create-new) on the `Selection`, inert. This feature makes the transfer engine **honor** it:
when the user has said "resolve affix X into target entry Y," the planner emits an entry-level
plan against Y and the executor creates X's senses / MSAs / allomorphs under the existing
target entry Y — instead of blindly creating a new entry. The two link actions differ only in
how the **entry-level fields** are written:

- **`overwrite`** — source wins on every field (import is golden). This is the existing
  source-wins entry-overwrite path.
- **`merge`** — the target's existing field values are preserved; source values are applied
  only where the target field is empty/absent (fill-the-gaps; target wins on conflicts). This
  is a **new write mode** the executor's apply step does not have today (see FR-007a and the
  live-verify risk below).

Child creation (senses / MSAs / allomorphs, with fingerprint de-duplication) is identical for
both link actions; only the entry-property apply step differs.

It is the third of five chunks (011 data model → 012 diff engine → **013 transfer threading** →
014 preview pane → 015 wizard flow). It is a headless, engine-only change: no Qt, no wizard, no
pane. It exists so that by the time the pane (014) lets the user pick a resolution, the pipeline
already does the right thing with it.

Four facts from the plan's code audit define the shape (corrections #1, #3, #4):

- **The affix path matches by GUID only.** `preview.py::_plan_layer3_verb_affixes_inner` plans
  every inflectional affix pointing at each walked POS via a local GUID index; the AFFIXES leaf
  bundle is a `NotImplementedError` stub that plans nothing. So the resolution must be threaded
  **through `Selection` into the Layer-3 walker**, not through the leaf dispatch.
- **`plan.identity_remap` starts empty and is only written at execute time; nothing consumes it
  during planning.** This feature **pre-seeds** it at plan-build time so downstream tail blocks,
  the report, and the stats panel see the remap for free.
- **Resolutions are keyed by source entry GUID and the walk is not gated by affix picks**, so a
  default resolution must be seeded for every SIMILAR row (default = `overwrite` into the
  suggested match, preserving today's source-wins behavior). This feature consumes whatever
  resolutions the `Selection` carries; producing the
  defaults from page state is 014's job, but the engine must behave correctly for the
  no-resolution case (regression: unchanged Phase-0 behavior).
- **Sense/MSA/allomorph creation under a merged-into different-GUID entry is an executor gap.**
  The overwrite path assumes same-GUID `target_entry_index[entry_guid]`; `_execute_layer3` only
  creates children for entries that appear in `plan.actions` as ENTRY. This feature closes that
  gap by handling the merge-into case explicitly.

Grounded in the source plan's cited lines: `preview.py` `_plan_layer3_verb_affixes_inner`,
`build_run_plan`; `transfer.py` `_execute_overwrite` ENTRY branch, `_execute_layer3`,
`identity_remap` writes; `report.py` / `StatsPanel` remap rendering.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resolve an affix into an existing target entry (overwrite or merge) (Priority: P1)

When the selection carries an `overwrite` or `merge` resolution for affix X into target entry Y
and the target does not already hold X by GUID, the planner emits an entry-level plan against Y
(recorded via identity remap) and the plan's identity remap maps X → Y, so downstream blocks and
reporting treat X as resolved to Y. The plan records which write mode (`overwrite` = source-wins,
`merge` = target-preserving fill-gaps) the executor must apply to Y's entry-level fields.

**Why this priority**: This is the core behavior the whole merge-preview feature exists to
enable; without it the user's resolution choice has no effect.

**Independent Test**: Run a fake source/target through `build_run_plan` with a
`SimilarResolution(X, "overwrite", Y)` and again with `SimilarResolution(X, "merge", Y)`; assert
a planned entry action with target GUID Y and `match_via="identity_remap"` in both cases, that
`plan.identity_remap[X] == Y`, and that the planned action carries the correct write mode.

**Acceptance Scenarios**:

1. **Given** a resolution `overwrite(X → Y)` or `merge(X → Y)` and a target lacking X by GUID,
   **When** the plan is built, **Then** it contains a planned ENTRY action with source X, target
   Y, `match_via="identity_remap"`, the write mode matching the action, and
   `plan.identity_remap[X]` equals Y.
2. **Given** either resolution, **When** the plan is built, **Then** X's senses / MSAs /
   allomorphs are planned as additions attributed to X (pulled-in-by X) against the resolved
   target entry Y (child creation is identical for `overwrite` and `merge`).
3. **Given** the seeded identity remap, **When** the plan flows to the report and stats panel,
   **Then** the remap is visible there without any additional wiring.
4. **Given** an `overwrite` resolution, **When** the executor applies entry-level fields to Y,
   **Then** the source value wins on every field; **given** a `merge` resolution, **Then** Y's
   existing field values are preserved and source values are written only where Y's field is
   empty/absent.

---

### User Story 2 - Choosing "create new" keeps the additive behavior (Priority: P1)

When the resolution says "create a new entry instead," the affix follows the existing Phase-0
add path exactly as it does today for a similar entry — the resolution simply makes that choice
explicit and auditable.

**Why this priority**: The create-new branch must be a no-op relative to current behavior so the
feature does not regress the common additive case; equal priority to US1 because it is the other
half of the choice.

**Independent Test**: Run the same fixture with `SimilarResolution(X, "create_new")`; assert the
plan contains a planned add for X identical to the no-resolution baseline.

**Acceptance Scenarios**:

1. **Given** a resolution `create_new(X)`, **When** the plan is built, **Then** X is planned as
   an added entry (Phase-0 add path) and no identity remap entry is created for X.
2. **Given** `create_new(X)`, **When** the plan is compared to the no-resolution baseline for X,
   **Then** the resulting actions for X are equivalent (auditability only, no behavior change).

---

### User Story 3 - No resolution means no change (regression) (Priority: P1)

When the selection carries no resolution for a SIMILAR affix, the planner and executor behave
exactly as they do today, so introducing the resolution machinery cannot alter existing
transfers.

**Why this priority**: The walk plans every affix regardless of picks; a silent behavior change
for un-resolved SIMILAR rows would be a correctness regression across all existing projects.

**Independent Test**: Run an existing planner fixture (no `similar_resolutions`) and assert the
plan is byte-identical to the pre-feature baseline.

**Acceptance Scenarios**:

1. **Given** a `Selection` with an empty `similar_resolutions`, **When** the plan is built,
   **Then** the plan is identical to the current (pre-feature) behavior for every affix.
2. **Given** a SIMILAR affix with no recorded resolution, **When** the plan is built, **Then**
   it follows today's default path (no identity remap seeded for it).

---

### User Story 4 - The executor populates children under the merged-into entry (Priority: P1)

When the plan carries an identity-remap entry overwrite, the executor locates the existing
target entry by its GUID and creates the source entry's senses, MSAs, and allomorphs under it,
without duplicating children that are already matched by fingerprint.

**Why this priority**: Closing correction #4's executor gap is what makes the merge-into actually
complete the transfer; a planned-but-not-executed merge would strand the children.

**Independent Test**: Execute a plan with an identity-remap ENTRY overwrite against a fake target
entry Y; assert Y gains X's children and that fingerprint-matched children are not duplicated.

**Acceptance Scenarios**:

1. **Given** a plan overwrite with `category==ENTRY` and `match_via=="identity_remap"`, **When**
   the executor runs, **Then** it looks up the target entry by the overwrite's target GUID and
   creates the source entry's senses / MSAs / allomorphs under it.
2. **Given** source MSAs/allomorphs that already appear as fingerprint matches for that entry in
   the plan, **When** the executor populates children, **Then** it skips them (no duplicates).
3. **Given** entry-level property overwrite for source GUID ≠ target GUID, **When** the executor
   runs, **Then** the existing same/different-GUID overwrite path merges properties into the
   target unchanged.

---

### Edge Cases

- **Target already holds X by GUID**: this is not a merge-into-different-entry case; existing
  same-GUID overwrite handling applies and no identity remap is seeded for X.
- **MSA/allomorph fingerprint owner component under merge-into-Y**: the fingerprint's owner-guid
  component must be overridden so source and resolved-target sides compare equal; this is called
  out as a live-verify risk (see Assumptions).
- **Resolution names a target GUID that no longer exists**: treated as a failed merge target;
  the executor must not crash (behavior falls back safely / is reported).
- **A SIMILAR row walked but not affix-picked, with a default merge resolution**: honored the
  same as a picked row (resolution is keyed by entry GUID, not gated by picks).
- **Both a resolution and a pre-existing same-GUID overwrite apply**: the same-GUID overwrite
  takes precedence (the entry already exists by identity; no remap needed).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Layer-3 verb-affix planner MUST read `selection.similar_resolution_for(
  entry_guid)` for each walked affix entry (None for non-SIMILAR / unresolved rows).
- **FR-002**: For an `overwrite` or `merge` resolution where the target lacks the entry GUID,
  the planner MUST emit a planned ENTRY action with source = entry GUID, target = the
  resolution's target GUID, `match_via="identity_remap"`, and a write mode recording the action
  (`overwrite` = source-wins, `merge` = target-preserving fill-gaps), and MUST record
  `identity_remap[entry_guid] = target_guid`.
- **FR-003**: For an `overwrite` or `merge` resolution, the planner MUST plan the source entry's
  senses, MSAs, and allomorphs as additions attributed to the source entry, with MSA/allomorph
  fingerprint matching evaluated against the resolved target entry (child planning is identical
  for both link actions).
- **FR-004**: For a `create_new` resolution, the planner MUST follow the existing Phase-0 add
  path for the entry (no identity remap seeded), preserving current behavior with added
  auditability.
- **FR-005**: With no resolution for an entry, the planner MUST behave exactly as today
  (regression guarantee); an empty `similar_resolutions` MUST produce an unchanged plan.
- **FR-006**: `build_run_plan` MUST pre-seed `plan.identity_remap` at plan-build time (before
  the run plan is finalized) so it flows into execution, the report, and the stats panel with
  no additional wiring; the identity-remap dict MUST be passed into the Layer-3 walker.
- **FR-007**: The executor's ENTRY overwrite branch MUST continue to handle source GUID ≠ target
  GUID (entry-level property apply into the target) unchanged for the `overwrite` write mode
  (source-wins).
- **FR-007a**: The executor MUST support a `merge` (target-preserving) write mode for entry-level
  fields that applies a source value only where the target field is empty/absent and preserves
  the target's value otherwise. This requires a fill-the-gaps variant of the flexicon fork's
  `ApplySyncableProperties` (which today applies source-wins unconditionally); the planned write
  mode from FR-002 selects between source-wins and fill-gaps at apply time.
- **FR-008**: `_execute_layer3` MUST add a pass over plan overwrites where `category==ENTRY` and
  `match_via=="identity_remap"`: locate the existing target entry by the overwrite's target
  GUID and create the source entry's senses / MSAs / allomorphs under it.
- **FR-009**: The per-entry child-creation body MUST be factored into a shared helper used by
  both the normal add path and the merge-into path (single source of truth for child creation).
- **FR-010**: The executor MUST skip source MSAs/allomorphs that already appear as fingerprint
  matches for the entry in the plan (no duplicate children).
- **FR-011**: This feature MUST NOT add any Qt widget, wizard page, or diff rendering; it
  consumes feature 011's `similar_resolutions` and is independent of the pane (014).

### Key Entities *(include if feature involves data)*

- **SimilarResolution (consumed)**: the per-entry merge/create decision defined in 011; read by
  the planner via `similar_resolution_for`.
- **Identity remap seed**: the `plan.identity_remap` mapping source entry GUID → resolved target
  GUID, now populated at plan-build time and consumed by execute/report/stats.
- **Identity-remap ENTRY action**: a planned entry action tagged `match_via="identity_remap"`
  carrying source and resolved-target GUIDs plus a write mode (`overwrite` source-wins /
  `merge` fill-gaps) — the executor's signal to apply entry fields per the write mode and
  populate children under an existing target entry.
- **Shared child-populator**: the factored helper that creates senses/MSAs/allomorphs under an
  entry object for both the add and merge-into paths.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An `overwrite(X → Y)` or `merge(X → Y)` resolution against a target lacking X
  yields exactly one planned ENTRY action (target Y, `match_via="identity_remap"`, write mode
  matching the action) and `plan.identity_remap[X] == Y`.
- **SC-001a**: Executing an `overwrite` entry action makes the source value win on every
  entry-level field of Y; executing a `merge` entry action leaves every non-empty target field
  of Y unchanged and fills only empty/absent fields from the source.
- **SC-002**: A `create_new(X)` resolution yields a planned add for X and zero identity-remap
  entries for X.
- **SC-003**: An empty `similar_resolutions` produces a plan byte-identical to the pre-feature
  baseline across the existing planner regression suite (0 diffs).
- **SC-004**: Executing an identity-remap ENTRY overwrite creates 100% of the source entry's
  non-fingerprint-matched children under the existing target entry and 0 duplicates of
  fingerprint-matched children.
- **SC-005**: The seeded identity remap appears in the report and stats-panel output with no
  changes to report/stats code.
- **SC-006**: The child-creation logic exists in exactly one shared helper (no duplicated
  add-vs-merge child code).

## Assumptions

- Feature 011 is merged: `Selection.similar_resolutions` and `similar_resolution_for` exist and
  are populated by whatever caller runs the planner (the wizard populates them in 014; tests
  populate them directly).
- Default-resolution seeding for all SIMILAR rows is **produced by the page state in 014**; this
  feature only requires correct behavior for both the resolved and the no-resolution cases.
- The MSA/allomorph fingerprint owner-guid override for the resolve-into case is a **live-verify
  risk**: it must be validated against a real project pair (Ejagham Mini → Ejagham Full GT-Test)
  before the feature is considered done.
- The **fill-gaps `merge` write mode is a new capability** in the flexicon fork's
  `ApplySyncableProperties` (which currently applies source-wins only). Both the new apply
  variant and the field-emptiness test (what counts as "empty" per multistring writing system)
  are **live-verify risks** to validate against the real project pair before done. Until the
  fork variant exists, `merge` cannot be executed distinctly from `overwrite`.
- `PreviewStale` / dry-run staleness gating is unchanged here; it is the backstop owned by the
  wizard-flow feature (015).
- The pre-existing gap that unchecked-but-walked entries may still be walked is **out of scope**
  (per correction #3) — this feature does not change which entries are walked, only how a
  resolved entry is planned/executed.
- **Upstream dependency (011).** **Consumers (014/015):** the pane and wizard flow are OUT OF
  SCOPE here; this feature is verifiable headlessly via `build_run_plan` + executor tests.
