# Feature Specification: Conflict-Mode UI & Field-Level Merge (per-category ADD_NEW / MERGE / OVERWRITE)

**Feature Branch**: `020-conflict-mode-field-merge`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Conflict-mode UI + field-level merge (ADD_NEW/MERGE/OVERWRITE per
category). Roadmap build-sequence step 5 — its own phase."

## Context

Every selection page shipped so far (008/009/010/016/018/019/021) deliberately **defers**
conflict handling: the per-category **Layer-1 default** is applied automatically and the
NEW / IN TARGET / SIMILAR target-status column carries the collision information without letting
the user act on it. The roadmap's "Undecided / to revisit" note pins this: *"Real per-category
conflict UI lands in the phase that implements field-level merge."* This feature is that phase.

The **data model and defaults already exist** — this is a UI/wiring feature, not new model work:

- `ConflictMode` enum (`ADD_NEW` / `MERGE` / `OVERWRITE`) —
  [Lib/models.py](../../src/gramtrans/Lib/models.py). `ADD_NEW` always creates a new copy;
  `MERGE` links-if-present-by-GUID else adds; `OVERWRITE` overwrites the target's existing
  object with source values (subject to Layer-1 kind and Layer-2 `IsProtected` gating).
- **Layer-1 kind gating** — `_DEFAULT_CONFLICT_MODES` (models.py) maps each `GrammarCategory` to
  a default and constrains which modes are offered:
  MULTI_INSTANCE → default `ADD_NEW` (all three offered); SINGLETON_NONDELETABLE → default
  `MERGE` (`ADD_NEW` hidden); GOLD_RESERVED → default `MERGE` (`ADD_NEW` hidden, `OVERWRITE`
  forbidden); CUSTOM_FIELDS → default `MERGE` (`ADD_NEW` hidden, `OVERWRITE` forbidden,
  conservative).
- **Per-category override slot** — `Selection.category_conflict_modes:
  dict[GrammarCategory, ConflictMode]`, resolved override-else-Layer-1-default via
  `conflict_mode_for` (models.py).
- **Field-level merge machinery** (spec 003) — [Lib/conflict.py](../../src/gramtrans/Lib/conflict.py)
  (`detect_conflicts`, `collect_overwrite_conflicts`, deterministic merge, prior-decision recall
  via `load_prior_log` / `load_prior_decision`) and the
  [ConflictDialog](../../src/gramtrans/Lib/ui/conflict_dialog.py) with `MergeResolution`
  (`TAKE_SOURCE` / `KEEP_TARGET` / `SKIP` / `EDIT_CUSTOM` / `MERGE`; `MERGE` hidden for scalar,
  non-mergeable fields). Layer-2 `IsProtected` gating lives in
  [Lib/protection.py](../../src/gramtrans/Lib/protection.py).

What is **missing** is the UI to let the user (a) choose the per-category conflict *mode*
(within the modes Layer-1 permits) and (b) resolve field-level conflicts for IN TARGET / SIMILAR
items when a category runs in `OVERWRITE` (or `MERGE` with divergent fields), wired into the
wizard Preview / merge-preview pane (spec 014). This feature surfaces and connects the existing
machinery; it does not redefine the modes, the Layer-1 gating, or the field merge algorithm.

Constitution constraints hold and are enforced, not re-decided: GOLD inviolability (I), GUID-first
identity (I), dual-carrier residue (I), Layer-2 protection (`IsProtected`) can veto an OVERWRITE
regardless of the chosen mode.

## Clarifications

### Session 2026-07-05

- Q: Where does the per-category conflict-mode control live? → A: **Inline on each page** — the
  per-category mode control sits on the selection page that owns that category (phonology,
  affixes, skeleton, grammatical deps, lexical-entry types, rules, stems, custom fields), next to
  its selection UI, rather than in a consolidated pre-Preview resolution step. The control still
  offers only the Layer-1-permitted modes for that category's kind, and the choice persists into
  `Selection.category_conflict_modes`. The merge-preview pane (US5) remains the roll-up review
  surface.

### Session 2026-07-05 (plan verification — live FLExTools MCP + LEX crew)

Resolved during `/speckit-plan` against live probes (Ejagham Full + Esperanto) and
recorded here so the spec matches buildable reality. See
[plan.md](./plan.md), [research.md](./research.md), [probe-results.md](./probe-results.md).

- Q: Does field-level resolution fire under `MERGE`? → A: **No — `OVERWRITE`-only.**
  `ConflictMode.MERGE` is link-if-present (writes nothing); wiring field-merge under
  MERGE would redefine the mode (FR-011) and is **post-020** (see
  [amendment-disposition-model.md](./amendment-disposition-model.md)). US2/FR-003 updated.
- Q: Does the conflict UI truly apply to *every* category uniformly? → A: The
  **mode selector** does; **field-level detection** applies only where a category
  exposes a working syncable-scalar surface. FR-012 updated; three tiers in plan.md.
- Q: Is the per-field conflict set really scalar/text only? → A: **No** — it is what
  `GetSyncableProperties` returns: scalar/text **plus atomic `*RA` GUID refs**
  (`MorphTypeRA`, `MorphoSyntaxAnalysisRA`, `SenseTypeRA`, `StatusRA`); only
  `*RS`/`*OC` multi-valued refs are excluded. FR-013 added.
- Q: Any category blocked outright? → A: **Phonemes and PH environments** — flexicon
  `GetSyncableProperties` raises `ITsString.get_String` on both (reproduced on two
  projects); field-diff for them is deferred until flexicon is fixed. FR-014 added.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose a conflict mode per category (Priority: P1)

On each selection page (or a consolidated resolution view), the user sees the current conflict
mode for each category and can change it among the modes Layer-1 permits for that category's
kind; the choice persists into the selection and governs planning.

**Why this priority**: The per-category mode selector is the core of the feature; every other
story depends on the user being able to pick a mode. MVP.

**Independent Test**: Open a page with a MULTI_INSTANCE category defaulting to `ADD_NEW`; change
it to `OVERWRITE`; confirm `Selection.category_conflict_modes` records the override and the plan
for that category switches from create-new to overwrite-existing.

**Acceptance Scenarios**:

1. **Given** a MULTI_INSTANCE category, **When** the user opens the mode selector, **Then** all
   three modes (`ADD_NEW`, `MERGE`, `OVERWRITE`) are offered with `ADD_NEW` preselected.
2. **Given** a GOLD_RESERVED category, **When** the user opens the mode selector, **Then**
   `ADD_NEW` is hidden and `OVERWRITE` is not selectable (forbidden); `MERGE` is preselected.
3. **Given** a CUSTOM_FIELDS category, **When** the user opens the mode selector, **Then**
   `ADD_NEW` is hidden and `OVERWRITE` forbidden; `MERGE` (conservative) is preselected.
4. **Given** a changed mode, **When** the user advances, **Then** `conflict_mode_for(category)`
   returns the override and the plan reflects it.

---

### User Story 2 - Resolve field-level conflicts for overwritten items (Priority: P1)

When a category runs in `OVERWRITE` and a selected item is IN
TARGET / SIMILAR, the user is shown the per-field conflicts and chooses, per field, to take
source, keep target, merge (where eligible), skip, or edit a custom value.

**Why this priority**: Field-level merge is the substantive capability the phase is named for;
without it, `OVERWRITE` is all-or-nothing and unsafe for partially-diverged objects.

**Independent Test**: Select an IN TARGET item in `OVERWRITE` mode whose source and target
differ on two fields; open the resolution dialog; set one field to TAKE_SOURCE and one to
KEEP_TARGET; confirm the executed write applies exactly those field decisions.

**Acceptance Scenarios**:

1. **Given** an IN TARGET item in `OVERWRITE` mode with divergent fields, **When** the user
   opens resolution, **Then** the ConflictDialog lists one row per conflicting field with the
   `MergeResolution` options, and `MERGE` is hidden for scalar/non-mergeable fields.
2. **Given** per-field decisions captured, **When** the transfer executes, **Then** each field is
   written per its decision (TAKE_SOURCE / KEEP_TARGET / MERGE / SKIP / EDIT_CUSTOM), not
   wholesale.
3. **Given** a field whose source and target are identical, **When** conflicts are detected,
   **Then** it is not presented as a conflict (no spurious prompts).

---

### User Story 3 - Prior decisions are recalled (Priority: P2)

When an item was resolved in a previous run, the user's earlier per-field decisions are recalled
and preselected, so repeated transfers don't re-litigate settled conflicts.

**Why this priority**: Reuses the spec-003 prior-log recall (`load_prior_log` /
`load_prior_decision`); it improves repeat-run ergonomics but is not required for a first
transfer.

**Independent Test**: Resolve an item's fields, complete a transfer, change nothing in source,
re-run; confirm the same item's resolution dialog preselects the prior decisions.

**Acceptance Scenarios**:

1. **Given** a prior-run decision recorded on a target object, **When** the resolution dialog
   opens for that object, **Then** the prior per-field decisions are preselected.
2. **Given** no prior decision, **When** the dialog opens, **Then** fields fall back to the
   mode's default resolution.

---

### User Story 4 - Protected and GOLD data cannot be overwritten (Priority: P1)

Layer-2 `IsProtected` and GOLD-reserved status veto an overwrite regardless of the chosen mode:
the user cannot pick a mode or a per-field decision that writes over protected/GOLD data.

**Why this priority**: Constitution I (GOLD inviolability) and Layer-2 protection are
non-negotiable safety rails; a conflict UI that could bypass them would be a regression.

**Independent Test**: Attempt to set `OVERWRITE` on a GOLD_RESERVED category and to TAKE_SOURCE a
protected field; confirm both are blocked (mode not selectable; field decision disabled or
vetoed at execute).

**Acceptance Scenarios**:

1. **Given** a GOLD_RESERVED category, **When** the user tries `OVERWRITE`, **Then** it is not
   selectable (Layer-1 forbids it).
2. **Given** a protected (`IsProtected`) target field, **When** the user tries TAKE_SOURCE for
   it, **Then** the decision is vetoed (disabled in the dialog and/or refused at execute) and the
   target field is preserved.

---

### User Story 5 - Preview reflects the chosen modes and field decisions (Priority: P2)

The merge-preview pane (spec 014) shows, before Move, what each chosen mode and field decision
will do — create vs. overwrite vs. link, and which fields change — so the user reviews the real
outcome, not the deferred Layer-1 default.

**Why this priority**: The preview is the review surface; it must reflect user choices for the
conflict UI to be trustworthy, but it renders decisions made in US1–US2.

**Independent Test**: Set a category to `OVERWRITE` with specific field decisions; open the
merge-preview pane; confirm the diff shows the overwrite and exactly the fields chosen to change.

**Acceptance Scenarios**:

1. **Given** chosen modes and field decisions, **When** the merge-preview renders, **Then** each
   affected item shows its planned action (create / overwrite / link) and the field-level diff
   reflects the decisions.
2. **Given** a category left at its Layer-1 default, **When** the preview renders, **Then** it
   shows the same behavior as the pre-020 pages (no regression).

---

### Edge Cases

- **Mode change after field decisions captured**: switching a category's mode invalidates
  field-level decisions that no longer apply (e.g. switching `OVERWRITE` → `ADD_NEW`); the user
  is not silently left with stale decisions.
- **`MERGE` on a scalar-only object**: `MERGE` degrades to the TAKE_SOURCE / KEEP_TARGET / SKIP /
  EDIT_CUSTOM set (the `MERGE` button is hidden per `merge_eligible`), consistent with spec 003.
- **Item is NEW (not in target)**: no field-level conflict exists; the mode collapses to a plain
  create regardless of `MERGE` / `OVERWRITE` selection.
- **Partial protection**: an object with some protected and some free fields in `OVERWRITE` —
  free fields follow the user's decisions; protected fields are vetoed and preserved.
- **Cross-run source change**: a prior decision exists but the source field changed since — the
  recalled decision is shown but flagged/re-evaluated rather than blindly applied (exact policy
  confirmed at plan time).
- **User cancels the resolution dialog**: `UserCancelled` is honored — no partial write; the
  wizard returns to the page without applying that item's overwrite.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each selection page MUST present, **inline** alongside that category's selection
  UI, a per-category conflict-mode control showing the current mode and offering exactly the
  modes Layer-1 permits for that category's kind (MULTI_INSTANCE: all three;
  SINGLETON_NONDELETABLE / GOLD_RESERVED / CUSTOM_FIELDS: `ADD_NEW` hidden; GOLD_RESERVED /
  CUSTOM_FIELDS: `OVERWRITE` forbidden). (A consolidated pre-Preview resolution step is NOT the
  chosen placement — per the 2026-07-05 clarification.)
- **FR-002**: Changing a category's mode MUST persist into `Selection.category_conflict_modes`
  and MUST be the value returned by `conflict_mode_for(category)`; unset categories MUST continue
  to resolve to the Layer-1 default (no behavior change for untouched categories).
- **FR-003**: For a selected item that is IN TARGET / SIMILAR under `OVERWRITE`, the system MUST
  present the per-field conflicts via the existing ConflictDialog, one row per conflicting field,
  with `MergeResolution` options; `MERGE` MUST be hidden for non-mergeable (scalar / GUID-ref)
  fields (`merge_eligible`). (Field-level resolution is `OVERWRITE`-only; `MERGE` mode is
  link-if-present and performs no field update — see Clarifications 2026-07-05.)
- **FR-004**: The system MUST NOT present as a conflict any field whose source and target values
  are identical (no spurious prompts).
- **FR-005**: The executed transfer MUST apply per-field decisions individually (TAKE_SOURCE /
  KEEP_TARGET / MERGE / SKIP / EDIT_CUSTOM), not a wholesale object overwrite, when field-level
  decisions have been captured.
- **FR-006**: Prior per-field decisions (spec 003 `load_prior_log` / `load_prior_decision`) MUST
  be recalled and preselected when resolving an item that was resolved in a previous run.
- **FR-007**: Layer-2 `IsProtected` and GOLD-reserved status MUST veto an overwrite regardless of
  the chosen mode or per-field decision: forbidden modes MUST NOT be selectable and protected
  fields MUST be preserved (decision disabled and/or refused at execute).
- **FR-008**: The merge-preview pane (spec 014) MUST reflect the chosen modes and field decisions
  — planned action per item (create / overwrite / link) and the field-level diff — so the review
  surface shows the real outcome, not the deferred Layer-1 default.
- **FR-009**: Switching a category's mode MUST invalidate field-level decisions that no longer
  apply, so the user is never left with stale, silently-applied decisions.
- **FR-010**: Cancelling the resolution dialog (`UserCancelled`) MUST result in no partial write
  for that item and return the user to the page.
- **FR-011**: This feature MUST NOT redefine the `ConflictMode` values, the Layer-1 kind gating
  (`_DEFAULT_CONFLICT_MODES`), the field-merge algorithm (`conflict.py`), or `MergeResolution`; it
  surfaces and wires the existing machinery.
- **FR-012**: The conflict-mode **selector** MUST appear uniformly across all category pages
  (phonology, affixes, skeleton, grammatical deps, lexical-entry types, rules, stems, custom
  fields) — it is cross-cutting, not page-specific. Field-level conflict **detection** applies
  only where the category exposes a working syncable-scalar surface (per FR-013/FR-014):
  categories without one show the selector but present no field-diff (a documented no-op), never
  an error.
- **FR-013**: The per-field conflict set MUST be exactly the properties returned by
  `GetSyncableProperties` for the object — scalar/text fields PLUS atomic `*RA` GUID references
  (e.g. `MorphTypeRA`, `MorphoSyntaxAnalysisRA`, `SenseTypeRA`, `StatusRA`). Multi-valued `*RS` /
  `*OC` references are excluded (not enumerated by flexicon) and MUST NOT be presented as field
  conflicts; the `MERGE` field option is offered only for text/list-valued fields (`merge_eligible`).
- **FR-014**: Categories whose `GetSyncableProperties` currently raises the flexicon
  `ITsString.get_String` defect — **Phonemes** and **PH environments** (reproduced on Ejagham
  Full and Esperanto, 2026-07-05) — MUST ship with the mode selector only; field-level detection
  for them is deferred until the flexicon defect is fixed, and the system MUST NOT attempt (and
  error on) field-diff for them.

### Key Entities *(include if feature involves data)*

- **Per-category conflict mode**: the `ConflictMode` chosen (or Layer-1-defaulted) for a
  `GrammarCategory`, stored in `Selection.category_conflict_modes`.
- **Field conflict**: a (object, field, source-value, target-value, merge_eligible) tuple
  detected by `conflict.py` for an IN TARGET / SIMILAR item under `OVERWRITE`. The field set is
  the `GetSyncableProperties` keys — scalar/text plus atomic `*RA` GUID refs; `*RS`/`*OC` excluded.
- **Field resolution**: the `MergeResolution` chosen per field (with optional custom value);
  recorded for prior-run recall.
- **Layer gating**: the Layer-1 kind rule (which modes are offered/forbidden) and Layer-2
  `IsProtected` veto that together constrain the user's choices.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every category, the mode selector offers exactly the Layer-1-permitted modes
  for its kind (verified across MULTI_INSTANCE, SINGLETON_NONDELETABLE, GOLD_RESERVED,
  CUSTOM_FIELDS) with the correct default preselected.
- **SC-002**: Changing a category's mode is reflected by `conflict_mode_for` and changes that
  category's planned actions accordingly; untouched categories behave exactly as pre-020.
- **SC-003**: For an IN TARGET item under `OVERWRITE` with N divergent fields, the resolution
  dialog presents exactly N field rows (identical fields excluded) and applies each field's
  decision individually on execute.
- **SC-004**: A GOLD_RESERVED category cannot be set to `OVERWRITE`, and a protected field cannot
  be overwritten via any decision — verified by attempted violation being blocked.
- **SC-005**: A re-run with unchanged source preselects the prior per-field decisions for
  previously-resolved items.
- **SC-006**: The merge-preview pane shows the correct planned action and field-level diff for
  every item under a non-default mode.
- **SC-007**: Cancelling resolution leaves the target unchanged for that item (no partial write).

## Assumptions

- The `ConflictMode` enum, `_DEFAULT_CONFLICT_MODES` Layer-1 gating,
  `Selection.category_conflict_modes` + `conflict_mode_for`, the `conflict.py` field-merge
  machinery, the `ConflictDialog` / `MergeResolution` UI, prior-decision recall, and Layer-2
  `protection.py` largely exist and are surfaced/wired by this feature — it does not re-specify
  or redefine them. Plan verification (2026-07-05) found three surfaces still to **add/adjust**
  as wiring (not model redefinition): a read-only `allowed_modes_for(category)` (surfacing the
  existing Layer-1 gating, FR-001), `_OW_OPS` coverage for the field-diff categories (FR-012),
  and a **fail-closed** `_is_protected` with an `ICmPossibility` cast (FR-007). See plan.md.
- **Field-diff scope** (verified via live MCP probes): the per-field conflict set is what
  `GetSyncableProperties` returns — scalar/text PLUS atomic `*RA` GUID refs; `*RS`/`*OC`
  multi-valued refs are excluded upstream by flexicon (FR-013). Allomorph phonological
  environments and POS template slot-lists are reference *collections* users may expect to
  merge; they are out of scope for 020 and flagged as future scope.
- **`MERGE` stays link-only** in this feature; field-level resolution is `OVERWRITE`-only. A
  `MERGE`-with-field-resolution path and the broader IGNORE/SKIP/UPDATE/OVERWRITE disposition
  model are post-020 (see [amendment-disposition-model.md](./amendment-disposition-model.md)).
- The merge-preview pane (spec 014) is the review surface this feature feeds; its diff rendering
  is extended to reflect user-chosen modes/decisions, not redesigned.
- **Where the mode selector lives** is resolved (2026-07-05): **inline per-category on each
  selection page**, not a consolidated pre-Preview step. The merge-preview pane is the roll-up
  review surface. The exact widget (dropdown vs. segmented control) remains a plan-time detail.
- The target project is bound early (Project+WS), so field-level conflict detection has live
  target data on every page.
- **Cross-run source-changed policy** (a prior decision exists but the source field changed) is
  confirmed at plan time; the safe default is to surface the change for re-evaluation rather than
  blindly reapply the old decision.
- This is the final roadmap increment; it depends on the category pages (010/016/018/019/021 and
  the current-slice pages) existing so there are categories to attach modes to. It does not block
  those pages, which ship with Layer-1 defaults until this phase lands.
