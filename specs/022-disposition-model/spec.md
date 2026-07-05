# Feature Specification: Per-Item Disposition Model (IGNORE / SKIP / UPDATE / OVERWRITE)

**Feature Branch**: `022-disposition-model`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Formalize the cross-project transfer disposition model
surfaced during 020 planning: replace the misleading `ADD_NEW / MERGE / OVERWRITE`
collision vocabulary with a clear per-category **intent** (Add new / Link / Update /
Overwrite) and a computed per-item **disposition** (Ignore / Skip / Add / Update /
Overwrite); add a non-destructive UPDATE that changes diverged fields but never blanks
a target field from an empty source; report genuinely-unchanged items as a true SKIP
rather than a phantom overwrite."

## Context

Every transfer in GramTrans is **cross-project**: source and target are two separate
FLEx projects. The shipped collision vocabulary (`ConflictMode.ADD_NEW / MERGE /
OVERWRITE`, [Lib/models.py](../../src/gramtrans/Lib/models.py)) has three problems
that 020 planning made concrete (see
[specs/020-conflict-mode-field-merge/amendment-disposition-model.md](../020-conflict-mode-field-merge/amendment-disposition-model.md)):

1. **"MERGE" does not merge.** `ConflictMode.MERGE` is *link-if-present-by-GUID, else
   add* — it writes nothing to an existing target object. It is really a **LINK / dedup**
   policy; the name misleads users and authors.
2. **There is no non-destructive update.** The only write-onto-existing policy
   (`OVERWRITE`) is wholesale source-wins, which silently **blanks** a target field when
   the corresponding source field is empty. The conservative variant only fills *empty*
   target fields and never updates a diverged non-empty one. Neither is the everyday
   "update what changed, keep the rest" behavior users expect.
3. **SKIP is decided by GUID-presence, not by field-identity.** An already-present item
   is skipped (under LINK) or produces a no-op overwrite (under OVERWRITE) even when
   nothing actually differs, so the run report cannot honestly say "unchanged."

This feature separates two concepts the enum conflates — **what the user intends** vs.
**what actually happens to a given item** — and adds the missing non-destructive UPDATE.
It is the constitutional successor to 020's conflict-mode UI: 020 ships the selector and
field-level resolution over the *existing* enum; 022 replaces the vocabulary and the
write semantics.

This feature **redefines `ConflictMode`** and therefore **requires a constitution
amendment** (Principle IV, Phased Merge Discipline). The draft amendment and Sync Impact
Report (v5.1.0 → v6.0.0) already exist in the 020 artifacts and are adopted here.

## Clarifications

### Session 2026-07-05

- Q: Is "MERGE" kept or renamed? → A: **Renamed to LINK.** It never merged; it links to
  an existing target and writes nothing. The persisted enum value `"merge"` is read
  through a compatibility shim (§Assumptions) for at least one release.
- Q: What distinguishes UPDATE from OVERWRITE? → A: **UPDATE is non-destructive** —
  source wins on fields that diverge, but a target field is **never blanked** because the
  source field is empty. OVERWRITE is wholesale source-wins (may blank).
- Q: What is a "true SKIP"? → A: A selected, already-present item whose user-editable
  fields are all in sync → reported as **unchanged/skipped**, with no write, distinct
  from IGNORE (never selected).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose a clear transfer intent per category (Priority: P1)

On each selection page the user chooses, per category, one intent from a vocabulary that
says what it does: **Add new**, **Link to existing (no changes)**, **Update**, or
**Overwrite** — within the modes Layer-1 permits for that category's kind. The chosen
intent governs planning.

**Why this priority**: The vocabulary is the feature; every other story depends on the
user being able to express intent unambiguously. MVP.

**Independent Test**: Open a page whose category previously offered "Merge"; confirm the
control now reads "Link to existing (no changes)", that "Update" is offered for a
MULTI_INSTANCE category, and that the selected intent persists and governs the plan.

**Acceptance Scenarios**:

1. **Given** a category that previously showed ADD_NEW / MERGE / OVERWRITE, **When** the
   user opens the intent control, **Then** it shows Add new / Link to existing / Update /
   Overwrite (subject to Layer-1 gating), with "Link" replacing the old "Merge".
2. **Given** a saved selection recorded under the old `"merge"` value, **When** it is
   loaded, **Then** it resolves to **LINK** with no error (compatibility shim).
3. **Given** a chosen intent, **When** the user advances, **Then** the plan reflects the
   intent and the computed per-item disposition.

---

### User Story 2 - Non-destructive UPDATE (Priority: P1)

When a category runs in **UPDATE** and a selected item already exists in the target, the
system writes the source values for fields that **diverge** but **preserves** any target
field the source does not fill — no target content is lost to an empty source.

**Why this priority**: This is the everyday, safe update users actually want; its absence
is the main reason OVERWRITE is dangerous. MVP.

**Independent Test**: Pick an existing target object where source and target differ on
field A and where field B is populated in the target but empty in the source; run UPDATE;
confirm field A takes the source value and field B still holds its target value.

**Acceptance Scenarios**:

1. **Given** a diverged non-empty source field, **When** UPDATE runs, **Then** the target
   field takes the source value.
2. **Given** a target field that is non-empty while the source field is empty, **When**
   UPDATE runs, **Then** the target field is preserved (never blanked).
3. **Given** OVERWRITE on the same object, **When** it runs, **Then** the empty source
   field **does** blank the target field (the destructive contrast that defines the two
   modes).

---

### User Story 3 - True SKIP and honest reporting (Priority: P1)

A selected item that already exists in the target and whose user-editable fields are all
in sync is reported as **unchanged (skipped)** with no write — distinct from an item that
was never selected (**ignored**) and from an item that was actually written
(update/overwrite).

**Why this priority**: Trustworthy reporting is a core value of Preview-Before-Mutate; a
phantom "overwrite" count on an unchanged item erodes trust. MVP.

**Independent Test**: Select an existing target object identical to its source in all
user-editable fields; run the transfer; confirm the report shows it as unchanged/skipped,
not overwritten, and that nothing was written.

**Acceptance Scenarios**:

1. **Given** an existing item with zero field differences, **When** the transfer runs,
   **Then** it is reported as SKIP (unchanged) and no write occurs.
2. **Given** an unchecked item, **When** the transfer runs, **Then** it is reported as
   IGNORE (not transferred) — a distinct outcome from SKIP.
3. **Given** an existing item with ≥1 field difference under UPDATE/OVERWRITE, **When**
   the transfer runs, **Then** it is reported as UPDATE/OVERWRITE, not SKIP.

---

### User Story 4 - Backward-compatible reading of saved state (Priority: P2)

Selections and residue tags written by earlier versions (which persist the value
`"merge"`) load without error and are interpreted as LINK, so upgrading does not break
saved runs.

**Why this priority**: Data-migration safety; important for existing users but not needed
to demonstrate the new model on a fresh run.

**Independent Test**: Round-trip a saved selection and a residue tag containing `"merge"`
through the loader; confirm both resolve to LINK and re-serialize under the new vocabulary.

**Acceptance Scenarios**:

1. **Given** a persisted `category_conflict_modes` entry of `"merge"`, **When** loaded,
   **Then** it resolves to LINK.
2. **Given** a residue tag with a `merge=` segment, **When** parsed, **Then** it is read
   without error under the new model.

---

### User Story 5 - Re-run recognizes genuinely untouched fields (Priority: P2)

On a re-run of a previously-transferred item, the system uses the prior-run baseline
(residue log) to distinguish a field that is **untouched since the projects diverged**
from one that merely happens to differ, so settled fields are not re-litigated. A first
transfer, lacking a baseline, is limited to "identical vs. diverged".

**Why this priority**: Improves repeat-run ergonomics and correctness of SKIP, but a
first transfer is fully useful without it.

**Independent Test**: Transfer an item, change nothing in the source, re-run; confirm
fields recorded in the prior-run baseline are treated as untouched and the item is
reported unchanged. Then change one source field and re-run; confirm only that field is
surfaced.

**Acceptance Scenarios**:

1. **Given** a prior-run baseline and an unchanged source, **When** re-run, **Then** the
   item is SKIP (unchanged) via the 3-way baseline.
2. **Given** no prior baseline (first transfer), **When** run, **Then** the system uses
   the 2-way identical-vs-diverged test and does not claim "untouched".
3. **Given** a source field changed since the prior run, **When** re-run, **Then** that
   field is surfaced for resolution rather than silently reapplied.

---

### Edge Cases

- **Item is NEW (not in target)**: intent collapses to ADD regardless of Link/Update/
  Overwrite selection.
- **UPDATE where both source and target diverge on a field**: source wins (it is an
  update toward source); the target's diverged value is replaced only for that field.
- **Layer-2 protection / GOLD**: a protected or GOLD target vetoes UPDATE and OVERWRITE
  regardless of intent (carried unchanged from 020, Constitution I).
- **All fields identical AND item unselected**: reported as IGNORE (selection wins over
  SKIP; it never enters the plan).
- **Reference-only category** (templates, slots, MSAs): no user-editable scalar fields to
  update; UPDATE/OVERWRITE degrade to LINK/ADD behavior with a field-diff no-op.
- **Blocked category** (Phonemes, PH environments — flexicon `GetSyncableProperties`
  defect from 020 FR-014): intent selectable, but field-level UPDATE detection deferred
  until the defect is fixed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST offer a per-category **intent** vocabulary of ADD_NEW,
  **LINK** (formerly MERGE), **UPDATE** (new), and OVERWRITE, subject to the existing
  Layer-1 permitted-mode gating for the category's kind.
- **FR-002**: The system MUST rename the collision policy `MERGE` to `LINK` throughout
  the user-facing UI and the model vocabulary, and MUST define LINK as link-if-present-by-
  GUID, else add — writing nothing to an existing target object.
- **FR-003**: The system MUST provide a **non-destructive UPDATE** write semantic: for an
  existing target object, write source values for fields that diverge, and **never** blank
  a target field because the corresponding source field is empty.
- **FR-004**: The system MUST provide OVERWRITE as the wholesale source-wins semantic
  (every field takes the source value, including blanking a target field from an empty
  source), preserving the pre-022 OVERWRITE behavior.
- **FR-005**: The system MUST compute a per-item **disposition** — IGNORE (unselected),
  SKIP (selected, present, all user-editable fields in sync), ADD (not present), UPDATE,
  or OVERWRITE — and MUST report each item by its disposition.
- **FR-006**: The system MUST emit a **true SKIP (unchanged)** — not a no-op write — when
  a selected, already-present item has zero user-editable field differences; the run
  report MUST distinguish SKIP from IGNORE and from an actual write.
- **FR-007**: The system MUST read persisted selections and residue tags written with the
  legacy value `"merge"` and interpret them as LINK, for at least one release
  (compatibility shim), without error.
- **FR-008**: On a re-run of a previously-transferred item, the system MUST use the
  prior-run baseline to distinguish an untouched field from a diverged one (3-way); on a
  first transfer, absent a baseline, it MUST fall back to identical-vs-diverged (2-way)
  and MUST NOT claim a field is "untouched".
- **FR-009**: A source field that changed since the recorded prior-run decision MUST be
  surfaced for re-evaluation rather than silently reapplied.
- **FR-010**: Layer-1 gating and Layer-2 `IsProtected` / GOLD vetoes MUST continue to
  constrain intent and per-field writes exactly as in 020 (no regression to the safety
  rails); a protected/GOLD target MUST veto UPDATE and OVERWRITE.
- **FR-011**: This feature MUST be accompanied by the ratified constitution amendment
  (Principle IV) bumping to v6.0.0; the `ConflictMode` redefinition MUST NOT ship without it.
- **FR-012**: The disposition vocabulary MUST apply uniformly across all category pages
  (cross-cutting), consistent with 020 FR-012 (uniform selector; field-level detection
  where a syncable-scalar surface exists).

### Key Entities *(include if feature involves data)*

- **Transfer intent**: the per-category choice — ADD_NEW / LINK / UPDATE / OVERWRITE —
  stored on the selection (successor to `category_conflict_modes`).
- **Item disposition**: the computed per-item outcome — IGNORE / SKIP / ADD / UPDATE /
  OVERWRITE — surfaced in preview and the run report.
- **Write semantic**: fill-gaps (existing), **update** (new: source-wins-where-nonempty,
  never blank), overwrite (existing).
- **Prior-run baseline**: the residue-log record used for the 3-way untouched test on
  re-runs.
- **Compatibility shim**: the read path mapping the legacy `"merge"` value to LINK.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every category, the intent control offers exactly the Layer-1-permitted
  set with LINK shown in place of MERGE and UPDATE offered where OVERWRITE is offered.
- **SC-002**: Under UPDATE, a diverged field takes the source value and a target field
  that is non-empty while the source is empty is preserved in 100% of cases — verified
  against a source→target pair exercising both.
- **SC-003**: Under OVERWRITE, an empty source field blanks the target field (the
  destructive contrast), confirming UPDATE and OVERWRITE are behaviorally distinct.
- **SC-004**: An already-present item with zero field differences is reported as SKIP
  (unchanged) with no write; an unselected item is reported as IGNORE — the two are never
  conflated.
- **SC-005**: 100% of saved selections and residue tags containing `"merge"` load and
  resolve to LINK without error.
- **SC-006**: On a re-run with an unchanged source, previously-settled fields are treated
  as untouched (3-way) and the item is SKIP; a first transfer makes no "untouched" claim.
- **SC-007**: All existing 020 safety behaviors (Layer-1 gating, GOLD/IsProtected veto,
  cancel = no partial write) hold unchanged.

## Assumptions

- **Constitution amendment adopted**: this feature depends on ratifying the v5.1.0 →
  v6.0.0 amendment drafted at
  [../020-conflict-mode-field-merge/amendment-disposition-model.md](../020-conflict-mode-field-merge/amendment-disposition-model.md).
  Without ratification the `ConflictMode` redefinition (FR-001/FR-002) cannot ship.
- **Builds on 020**: the conflict-mode selector, field-level resolution machinery,
  Layer-1 `allowed_modes_for`, and fail-closed `_is_protected` from 020 are assumed
  present; 022 changes the vocabulary and write semantics over that base, not the safety
  rails.
- **Data migration is a shim, not a rewrite**: persisted `"merge"` values are read as
  LINK for ≥1 release (mirroring the constitution's `flexlibs2 → flexicon` deprecation
  shim). No existing value maps to UPDATE; UPDATE is opt-in.
- **Open decision (default chosen — confirm at `/speckit-clarify`)**: UPDATE becomes the
  default intent for MULTI_INSTANCE categories (safer than OVERWRITE, more useful than
  LINK), demoting OVERWRITE to an explicit opt-in. Alternative: keep ADD_NEW/LINK defaults
  unchanged and make UPDATE purely opt-in.
- **Open decision (default chosen — confirm at `/speckit-clarify`)**: on re-run, the
  residue baseline is used to auto-SKIP genuinely-untouched items but only to *annotate*
  (not auto-apply) when the source changed — settled by prompting, per 020 R7.
- **Open decision (default chosen — confirm at `/speckit-clarify`)**: LINK is pure
  link-if-present in this feature; a "re-point a stale reference" variant is future scope.
- **Field-diff scope carried from 020**: the fields eligible for UPDATE/OVERWRITE
  detection are the `GetSyncableProperties` keys (scalar/text + atomic `*RA` GUID refs;
  `*RS`/`*OC` excluded). Phonemes and PH environments remain blocked by the upstream
  flexicon defect (020 FR-014).

## Dependencies

- **020-conflict-mode-field-merge** — must ship first; 022 replaces its vocabulary and
  write semantics.
- **Constitution v6.0.0 amendment** — must be ratified (FR-011).
- **flexicon defect fix** (Phonemes/Environments `GetSyncableProperties`) — not a blocker
  for 022 as a whole, but gates UPDATE detection for those two categories.
