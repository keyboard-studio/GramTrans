# Tasks: Conflict-Mode UI & Field-Level Merge (per-category ADD_NEW / MERGE / OVERWRITE)

**Feature**: 020-conflict-mode-field-merge | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Ground truth**: [probe-results.md](./probe-results.md) — live FLExTools MCP (Ejagham Full +
Esperanto). **Do not guess LCM/flexicon API.** Reuse the shipped conflict/merge machinery
(`conflict.py`, `ui/conflict_dialog.py`, `models.py`, `protection.py`); this feature surfaces
and wires it (see plan.md §Summary for the five gaps).

**Workflow protocol**: this `tasks.md` is a spec artifact and lives on `main`. **Implementation
work (src/, tests/) is done in the `GramTrans-020-conflict-mode-field-merge` worktree** on branch
`020-conflict-mode-field-merge` and merged back when validated (CLAUDE.md Git Workflow Protocol).

**Tests**: requested (plan Project Structure lists unit + integration suites).

**Scope tiers** (plan §Buildable scope): Tier A = real field-diff (POS, InflectionFeature,
NaturalClass, LexEntry, Sense, Allomorph; MorphRule pending T002). Tier B = selector-only.
Tier C = selector-only, field-diff **blocked** by the flexicon `ITsString.get_String` defect
(Phonemes, PH environments — FR-014).

---

## Phase 1: Setup

- [ ] T001 Confirm the shipped machinery is present and importable with a grep/sanity pass across `src/gramtrans/Lib/{models.py,conflict.py,protection.py,preview.py,selection.py,ui/conflict_dialog.py,ui/selection_wizard.py}` — verify `ConflictMode`, `MergeResolution`, `Selection.conflict_mode_for`/`_replace_conflict_modes`, `_DEFAULT_CONFLICT_MODES`, `detect_conflicts`, `collect_overwrite_conflicts`, `_OW_OPS`, `build_session_from_resolutions`, `ConflictDialog`, `apply_isprotected_layer2` (no code change; record findings).
- [ ] T002 [P] Live MCP probe (read-only) via `flextools_run_module` to resolve research **R2a**: call `MorphRules.GetSyncableProperties` on a rule-bearing project (Esperanto for compound rules; a project with morph rules) to confirm the key set (`Name/Description/StratumGuid/Disabled`) and confirm whether MorphRule belongs in Tier A; append the confirmed facts to [probe-results.md](./probe-results.md).

---

## Phase 2: Foundational (blocking prerequisites)

**⚠️ CRITICAL**: US1/US4 depend on the Layer-1 surface and the fail-closed protection change.

- [ ] T003 Promote the category kind-sets to module-level frozensets in `src/gramtrans/Lib/models.py`: extract `_MULTI_INSTANCE_CATS`, `_SINGLETON_CATS`, `_GOLD_RESERVED_CATS`, `_CUSTOM_FIELDS_CATS` from the locals inside `_build_default_conflict_modes` (models.py:102-157) and have `_build_default_conflict_modes` read them, preserving `_DEFAULT_CONFLICT_MODES` output byte-for-byte (research R3, R3a — grep callers first).
- [ ] T004 Add `allowed_modes_for(category) -> frozenset[ConflictMode]` in `src/gramtrans/Lib/models.py` as a read-only companion to `conflict_mode_for`, returning the Layer-1 permitted set per kind (MULTI_INSTANCE all three; SINGLETON `{MERGE,OVERWRITE}`; GOLD_RESERVED/CUSTOM_FIELDS `{MERGE}`); invariant `conflict_mode_for(c) in allowed_modes_for(c)` (FR-001, data-model.md; depends T003).
- [ ] T005 Change `_is_protected` in `src/gramtrans/Lib/protection.py` to read `IsProtected` via an `ICmPossibility(x).IsProtected` cast and **fail closed** (indeterminate/failed-cast ⇒ return `True`) with a diagnostic log line; keep `apply_isprotected_layer2` behavior (downgrade protected ⇒ MERGE) (FR-007/US4, research R4).
- [ ] T006 Add the per-category selector view model + static tier map in `src/gramtrans/Lib/selection.py`: `ConflictModeChoice(category, current, allowed, field_diff_tier, blocked_reason)` and a `CATEGORY_FIELD_DIFF_TIER` map (A/B/C) sourced from [probe-results.md](./probe-results.md) / plan §Buildable scope (data-model.md).

**Checkpoint**: Layer-1 query, fail-closed protection, and the selector view model exist and are unit-importable.

---

## Phase 3: User Story 1 — Choose a conflict mode per category (Priority: P1) 🎯 MVP

**Goal**: Each selection page shows an inline per-category mode control offering exactly the
Layer-1-permitted modes, preselecting the current mode; the choice persists and governs planning.

**Independent Test**: Open a MULTI_INSTANCE page defaulting to ADD_NEW → all three offered; change to OVERWRITE → `conflict_mode_for` returns it and the plan switches to overwrite; a GOLD_RESERVED page hides ADD_NEW and disables OVERWRITE.

- [ ] T007 [US1] Implement `build_conflict_mode_choices(selection, categories)` in `src/gramtrans/Lib/selection.py` producing one `ConflictModeChoice` per on-category from `allowed_modes_for` + `conflict_mode_for` + the tier map (fake-handle testable).
- [ ] T008 [US1] Add the inline per-category mode control to each page in `src/gramtrans/Lib/ui/selection_wizard.py` (reusable widget rendered on every category page, FR-012): populate options from the choice's `allowed`, preselect `current`, label MERGE as "Link to existing (no changes)" and OVERWRITE as "Update/Overwrite" per plan §labels; disable/hide modes not in `allowed`.
- [ ] T009 [US1] Persist selections: collapse changed controls into `Selection.category_conflict_modes` via `_replace_conflict_modes`; leave unchanged categories' keys **absent** so `conflict_mode_for` returns the Layer-1 default (SC-002 no-regression), in `src/gramtrans/Lib/ui/selection_wizard.py`.
- [ ] T010 [US1] Invalidate stale field decisions on mode change (FR-009/research R8): when a category's mode changes, drop that category's entries from the pending `InteractiveSession.merge_decisions_by_guid`, in `src/gramtrans/Lib/ui/selection_wizard.py`.
- [ ] T011 [P] [US1] Unit test `tests/unit/test_allowed_modes.py`: per-kind permitted sets (SC-001) + invariant `conflict_mode_for(c) in allowed_modes_for(c)`.
- [ ] T012 [P] [US1] Unit test `tests/unit/test_conflict_mode_persist.py`: override persists via `_replace_conflict_modes`; untouched category still returns Layer-1 default (SC-002).
- [ ] T013 [P] [US1] Unit test `tests/unit/test_mode_change_invalidation.py`: switching OVERWRITE→ADD_NEW drops that category's captured decisions (FR-009).
- [ ] T014 [P] [US1] Unit test `tests/unit/test_tier_map.py`: every category page maps to a tier; Tier-C (PHONEMES, PH_ENVIRONMENT) has a non-empty `blocked_reason` (FR-012/FR-014).

**Checkpoint**: the per-category selector is live on every page, persists, and governs the plan — MVP.

---

## Phase 4: User Story 4 — Protected and GOLD data cannot be overwritten (Priority: P1)

**Goal**: Layer-1 forbids OVERWRITE for GOLD_RESERVED/CUSTOM_FIELDS (not selectable); Layer-2
`IsProtected` vetoes an overwrite of a protected target regardless of chosen mode/field decision.

**Independent Test**: GOLD_RESERVED category → OVERWRITE not selectable; a protected target field → TAKE_SOURCE vetoed and target preserved after Move.

- [ ] T015 [US4] Confirm the selector blocks forbidden modes end-to-end (GOLD_RESERVED/CUSTOM_FIELDS OVERWRITE not selectable) via the `allowed_modes_for` wiring from T008; add a guard that rejects an out-of-set override in `src/gramtrans/Lib/ui/selection_wizard.py` (FR-007, SC-004).
- [ ] T016 [US4] Wire `apply_isprotected_layer2` into the overwrite path so a protected target downgrades the effective mode to MERGE and its field decisions are vetoed (disabled in the dialog and/or refused at execute), in `src/gramtrans/Lib/conflict.py` / `src/gramtrans/Lib/transfer.py` (FR-007).
- [ ] T017 [P] [US4] Unit test `tests/unit/test_protection_failclosed.py`: failed `ICmPossibility` cast ⇒ `_is_protected` returns True + logs; concrete unprotected possibility ⇒ False (research R4).
- [ ] T018 [P] [US4] Unit test `tests/unit/test_gold_overwrite_blocked.py`: GOLD_RESERVED not offered OVERWRITE; out-of-set override rejected (SC-004).

**Checkpoint**: safety rails hold — no path writes over GOLD/protected data.

---

## Phase 5: User Story 2 — Resolve field-level conflicts for overwritten items (Priority: P1)

**Goal**: For an IN TARGET/SIMILAR item under OVERWRITE, the user resolves per-field conflicts
(take source / keep target / merge / skip / edit) and the executed write applies each decision.

**Independent Test**: An IN TARGET POS differing on two fields under OVERWRITE → dialog shows exactly the differing fields → set one TAKE_SOURCE, one KEEP_TARGET → Move applies exactly those.

- [ ] T019 [US2] Extend `_OW_OPS` in `src/gramtrans/Lib/conflict.py` with the confirmed Tier-A categories beyond pos/entry/sense/allomorph — add `inflection_features`, `natural_classes` (and `morph` iff T002 confirms) — each with a `_find_target_<x>_by_guid` finder using lowercase-normalized GUID match (research R2, contracts C3).
- [ ] T020 [US2] Verify/complete the collect→resolve→execute wiring for the new categories: `collect_overwrite_conflicts` → `ConflictResolver.resolve` → `build_session_from_resolutions` → `transfer.execute` applies per-field decisions (props filtered to TAKE_SOURCE keys), in `src/gramtrans/Lib/conflict.py` / `src/gramtrans/Lib/transfer.py` (FR-005, contracts C2).
- [ ] T021 [US2] Ensure Tier-B categories (no `_OW_OPS` entry) return no prompts without error and Tier-C (PHONEMES, PH_ENVIRONMENT) are never sent to `collect_overwrite_conflicts` (guard against the flexicon `GetSyncableProperties` throw), in `src/gramtrans/Lib/conflict.py` (FR-014).
- [ ] T022 [P] [US2] Unit test `tests/unit/test_field_scope.py`: identical fields suppressed; scalar text ⇒ `merge_eligible=True`; int (`HomographNumber`) and atomic `*RA` (`MorphTypeRA`) ⇒ present with `merge_eligible=False`; no `*RS`/`*OC` keys (FR-013/research R5).
- [ ] T023 [P] [US2] Integration test `tests/integration/test_conflict_live.py`: MCP Ejagham Mini → **fresh GT-Test** target; IN TARGET item under OVERWRITE with N divergent fields ⇒ N rows; per-field decisions applied on execute (SC-003).

**Checkpoint**: field-level resolution works for Tier-A categories under OVERWRITE; Tier-B/C safe.

---

## Phase 6: User Story 3 — Prior decisions are recalled (Priority: P2)

**Goal**: Earlier per-field decisions are recalled and preselected on re-run; a source field
changed since the prior run is surfaced for re-evaluation, not blindly reapplied.

**Independent Test**: Resolve fields, Move, change nothing in source, re-run → dialog preselects prior decisions; change one source field → that field re-surfaces.

- [ ] T024 [US3] Confirm `load_prior_log`/`load_prior_decision` recall is threaded through `collect_overwrite_conflicts` (`prior_logs_by_guid`) for the Tier-A categories, in `src/gramtrans/Lib/conflict.py` (FR-006; mostly wiring of existing machinery).
- [ ] T025 [US3] Add "source changed since prior run" annotation (research R7): when `src_props[field]` differs from the prior decision's `right_value`, flag the prompt for re-evaluation rather than silently preselecting, in `src/gramtrans/Lib/conflict.py` / `src/gramtrans/Lib/ui/conflict_dialog.py`.
- [ ] T026 [P] [US3] Unit test `tests/unit/test_prior_recall.py`: prior decision preselected; no prior ⇒ mode default; changed-source ⇒ re-evaluation flag set (SC-005).

**Checkpoint**: repeat runs don't re-litigate settled conflicts.

---

## Phase 7: User Story 5 — Preview reflects the chosen modes and field decisions (Priority: P2)

**Goal**: The merge-preview pane shows the planned action (create/overwrite/link) and the
field-level diff from the captured decisions; default-mode categories render as pre-020.

**Independent Test**: Set a category to OVERWRITE with specific field decisions → preview shows the overwrite and exactly the chosen changed fields; a default-mode category shows pre-020 behavior.

- [ ] T027 [US5] Render per-item planned action + field-level diff in the merge-preview pane from `conflict_mode_for` + Layer-2 + captured `MergeDecision`s, in `src/gramtrans/Lib/preview.py` (FR-008, contracts C5).
- [ ] T028 [US5] Ensure a category left at its Layer-1 default renders identically to pre-020 (no-regression) and Tier-B/C render the action but no field-diff rows, in `src/gramtrans/Lib/preview.py` (SC-006).
- [ ] T029 [P] [US5] Unit test `tests/unit/test_preview_reflects_choices.py`: OVERWRITE + field decisions ⇒ correct action + exact changed-field diff; default-mode category ⇒ pre-020 output (SC-006).

**Checkpoint**: the review surface reflects real user choices.

---

## Phase 8: Polish & Cross-Cutting

- [ ] T030 [P] File the flexicon defect separately (plan §Follow-ups): `GetSyncableProperties` raises `AttributeError("'ITsString' object has no attribute 'get_String'")` for Phoneme and Environment (Ejagham Full + Esperanto, 2026-07-05); cross-reference the bug id into [probe-results.md](./probe-results.md) Tier C and FR-014.
- [ ] T031 [P] [US2] Integration test `tests/integration/test_conflict_live.py::test_cancel_no_write`: open resolver, Cancel ⇒ target byte-unchanged for that item (SC-007, FR-010).
- [ ] T032 Run [quickstart.md](./quickstart.md) unit + live scenarios against Ejagham Mini → GT-Test; attach pre/post Import Residue artifacts (constitution Verification gate).
- [ ] T033 [P] Update module docstrings / `docs/` for the new `allowed_modes_for` surface, fail-closed `_is_protected`, and the tier map.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: no deps; T002 informs T019 (MorphRule tier).
- **Foundational (P2)**: after Setup — BLOCKS all stories. T004 depends on T003.
- **US1 (P3)**: after Foundational. MVP.
- **US4 (P4)**: after US1 (selector) + T005/T016 (protection).
- **US2 (P5)**: after Foundational; T019 needs T002; integrates with US4 veto (T016).
- **US3 (P6)**: after US2 (recall threads through the collect path).
- **US5 (P7)**: after US2 (renders decisions produced there).
- **Polish (P8)**: after the stories it covers.

### Within Each Story

- Tests marked [P] can run in parallel (distinct files).
- models/selection surfaces before wizard wiring; conflict/transfer wiring before preview.

### Parallel Opportunities

- T002 ‖ T001 (Setup).
- Foundational T003→T004 sequential; T005, T006 parallel to each other.
- All `[P]` unit tests within a story run together.

---

## Parallel Example: User Story 1

```bash
# After T007-T010 land, run US1 unit tests together:
Task: "tests/unit/test_allowed_modes.py"
Task: "tests/unit/test_conflict_mode_persist.py"
Task: "tests/unit/test_mode_change_invalidation.py"
Task: "tests/unit/test_tier_map.py"
```

---

## Implementation Strategy

### MVP (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **STOP & VALIDATE** the per-category
   selector persists and governs the plan. Demo.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. + US1 (selector) → MVP.
3. + US4 (safety rails) → GOLD/protected veto proven.
4. + US2 (field resolution) → the named capability.
5. + US3 (recall) and US5 (preview) → full feature.

### Notes

- Do the code in the `GramTrans-020-conflict-mode-field-merge` worktree; keep `tasks.md` and other
  spec edits on `main`.
- MERGE stays link-only (field resolution OVERWRITE-only, FR-011); the IGNORE/SKIP/UPDATE/OVERWRITE
  redesign is the separate 022 feature — do not pull it into 020.
- Do not add Tier-C categories to `_OW_OPS` until the flexicon defect (T030) is fixed.
