# Tasks: Per-Item Disposition Model (LINK rename + UPDATE intent + auto-SKIP)

**Feature**: 022-disposition-model | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Workflow protocol**: this `tasks.md` is a spec artifact and lives on `main`.
**Implementation work (src/, tests/) is done in the `GramTrans-020-conflict-mode-field-merge`
worktree** on branch `020-conflict-mode-field-merge` (the active worktree for conflict-mode
work) and merged back when validated (CLAUDE.md Git Workflow Protocol). 022 builds directly
on the 020 machinery; do not attempt to implement without 020 merged.

**Tests**: requested (plan Project Structure lists unit + integration suites covering ~45
renamed refs and new UPDATE/SKIP assertions).

**Key constraints**:
- MergeResolution enum (`models.py:201/205`) is NOT touched -- it is a distinct vocabulary.
- Residue wire format (`residue.py:27,96,179; conflict.py:385`) is NOT touched.
- Phoneme/Environment stay SELECTOR-ONLY; gated behind flexicon version check (Ruling Y).
- LINK stale-reference re-pointing is 023 scope; do NOT implement here.

---

## Phase 1: Setup

- [ ] T001 Grep catalog: run `grep -rn "MERGE\|\"merge\"\|ConflictMode\.MERGE" src/gramtrans/Lib/ tests/` and record every hit with file + line; also grep `selection_wizard.py` for `_CONFLICT_LABELS`, `allowed_modes_for`, and the default-wiring block (~:1275). Record count and file breakdown in a comment here before touching any code. (Expected: ~45 refs across models.py:149,151,153,156,450; categories.py:204; protection.py:54; ui/selection_wizard.py:128,184,186,1275; tests/unit/test_conflict_mode_model.py:66,97,163,261; tests/unit/test_wizard_page_flow.py:423.)
- [ ] T002 Verify 022 prerequisites: confirm 020 is merged (or at minimum the 020 foundational tasks T003-T006 are present in the worktree) by checking that `allowed_modes_for`, `_MULTI_INSTANCE_CATS`, and `ConflictModeChoice` are importable from `src/gramtrans/Lib/models.py` and `src/gramtrans/Lib/selection.py`. Record result; do not proceed if 020 is absent.

---

## Phase 2: Foundational (blocking prerequisites)

**CRITICAL**: The rename and UPDATE enum addition must land before any story work; they are the vocabulary all other tasks use.

- [ ] T003 Add `ConflictMode.LINK = "link"` and `ConflictMode.UPDATE = "update"` to the enum in `src/gramtrans/Lib/models.py:74` (class body); remove `MERGE = "merge"`. Update `_build_default_conflict_modes` and `_DEFAULT_CONFLICT_MODES` at lines 149/151/153/156: replace every `MERGE` reference with `LINK`; set the MULTI_INSTANCE default to `UPDATE` (was `ADD_NEW` or `MERGE` per 020 wiring -- UPDATE is the new default per Ruling).
- [ ] T004 Add the read-time compatibility shim in `src/gramtrans/Lib/models.py` at `conflict_mode_for` (~:447): before resolving the stored string, if the value is `"merge"`, remap it to `"link"` (i.e., `ConflictMode.LINK.value`) and continue. This is the ONE shim point; no shim elsewhere. Add a deprecation log line noting the legacy value. Also update the remaining MERGE sentinel refs at line 450.
- [ ] T005 Update `allowed_modes_for` in `src/gramtrans/Lib/models.py` to add `UPDATE` to the `_MULTI_INSTANCE_CATS` permitted set and exclude `UPDATE` from `_GOLD_RESERVED_CATS` / `_CUSTOM_FIELDS_CATS` permitted sets (OVERWRITE and UPDATE are both opt-in-dangerous; GOLD safety rail applies to both). `_SINGLETON_CATS` permitted set: include `UPDATE` (non-destructive, safe for singleton; confirm against spec FR-001 Layer-1 gating).
- [ ] T006 Rename `MERGE -> LINK` at the four call sites in `src/gramtrans/Lib/categories.py:204` and `src/gramtrans/Lib/protection.py:54` (the `apply_isprotected_layer2` safe-downgrade target, which should now downgrade to `LINK`). Verify grep catalog from T001 covers all sites.

**Checkpoint**: `ConflictMode.LINK`, `ConflictMode.UPDATE`, and `ConflictMode.MERGE` (gone) are importable; `conflict_mode_for` returns LINK for a `"merge"` input without error; `allowed_modes_for` includes UPDATE for MULTI_INSTANCE.

---

## Phase 3: User Story 1 -- Clear intent vocabulary in UI (P1)

**Goal**: Every selection page's intent control shows LINK (not MERGE), offers UPDATE for MULTI_INSTANCE categories, and persists the chosen intent. Saved selections using `"merge"` load without error as LINK.

**Independent Test**: Open a MULTI_INSTANCE page; control shows ADD_NEW / LINK / UPDATE / OVERWRITE; "Link to existing (no changes)" replaces "Merge"; selecting UPDATE persists and governs plan. Load a saved selection with `category_conflict_modes["pos"] = "merge"`; resolves to LINK, no error. (Spec US1 scenarios 1-3.)

- [ ] T007 [US1] Update `_CONFLICT_LABELS` in `src/gramtrans/Lib/ui/selection_wizard.py:128`: rename the `MERGE` key to `LINK`; label text stays "Link to existing (no changes)". Add an `UPDATE` entry with label "Update (non-destructive)".
- [ ] T008 [US1] Update the allowed-modes functions at `src/gramtrans/Lib/ui/selection_wizard.py:184` and `:186`: replace `ConflictMode.MERGE` with `ConflictMode.LINK`; add `ConflictMode.UPDATE` to the MULTI_INSTANCE offered set. Verify Tier C (Phonemes, PH environments) still shows SELECTOR-ONLY (no UPDATE field-diff) pending the flexicon version check (T014).
- [ ] T009 [US1] Update default wiring at `src/gramtrans/Lib/ui/selection_wizard.py:1275`: set MULTI_INSTANCE default to `ConflictMode.UPDATE` (was ADD_NEW or MERGE per 020). Verify SINGLETON default is LINK.
- [ ] T010 [US1] Verify that the `Selection.category_conflict_modes` field annotation at `src/gramtrans/Lib/models.py:355` correctly types the values as `ConflictMode`; update the type hint and any inline comments referencing MERGE.

**Checkpoint**: UI renders LINK and UPDATE correctly; "merge" persisted value round-trips to LINK; MULTI_INSTANCE pages default to UPDATE.

---

## Phase 4: User Story 2 -- Non-destructive UPDATE write semantic (P1)

**Goal**: Under UPDATE, a diverged field takes the source value; a target field that is non-empty while the source field is empty is preserved. OVERWRITE continues to blank target fields from empty source (the destructive contrast).

**Independent Test**: Source field A diverged (non-empty src, non-empty target, different values) + field B non-empty in target and empty in source; run UPDATE; A takes source value, B unchanged. Run OVERWRITE on same pair; B is blanked. (Spec US2 scenarios 1-3.)

- [ ] T011 [US2] Implement the UPDATE write semantic in `src/gramtrans/Lib/conflict.py` alongside the existing OVERWRITE path: iterate `GetSyncableProperties` keys; for each key, if the source value is empty (None / empty string / empty GUID), skip the write; otherwise write the source value to the target field. Contrast: OVERWRITE continues to write source unconditionally.
- [ ] T012 [US2] Wire the UPDATE path into `src/gramtrans/Lib/transfer.py` execute path: when `conflict_mode_for(category) == ConflictMode.UPDATE` and the item is already present (IN TARGET), call the UPDATE write semantic (T011) rather than the OVERWRITE write. ADD path is unchanged (new items are always added regardless of intent).
- [ ] T013 [US2] Guard UPDATE and OVERWRITE paths in `src/gramtrans/Lib/protection.py` / `src/gramtrans/Lib/conflict.py`: a GOLD or `IsProtected` target MUST veto both UPDATE and OVERWRITE and downgrade to LINK behavior (no field writes), consistent with 020 R4 and constitution Principle I.

**Checkpoint**: UPDATE writes only diverged non-empty source fields; OVERWRITE is unchanged; GOLD/protected veto applies to both.

---

## Phase 5: User Story 3 -- True SKIP and honest reporting (P1)

**Goal**: An already-present item with zero user-editable field differences is reported SKIP with no write. An unselected item is IGNORE. SKIP and IGNORE are never conflated in the report.

**Independent Test**: Item present in target with all fields identical to source; run transfer under UPDATE or OVERWRITE; report shows SKIP, no write. Unselected item shows IGNORE. Item with >=1 diverged field shows UPDATE/OVERWRITE, not SKIP. (Spec US3 scenarios 1-3.)

- [ ] T015 [US3] Add per-item disposition computation in `src/gramtrans/Lib/conflict.py`: before executing a write, compare source and target field-by-field (via `GetSyncableProperties`; 2-way on first run). If all fields are identical, downgrade the action to SKIP (no write). Disposition enum or constant: IGNORE / SKIP / ADD / UPDATE / OVERWRITE.
- [ ] T016 [US3] Surface disposition in the run report: the `PlannedAction` (or equivalent data structure) must carry the computed disposition so the report (`preview.py` / UI) can display SKIP separately from ADD / UPDATE / OVERWRITE / IGNORE. No write occurs for SKIP disposition.
- [ ] T017 [US3] Ensure IGNORE (item never selected) is distinct from SKIP (selected, present, all-identical) in both the plan data and the report output. Unselected items must not enter the plan as SKIP; they are IGNORE (never planned).

**Checkpoint**: run report distinguishes IGNORE / SKIP / ADD / UPDATE / OVERWRITE; no phantom overwrite counts for unchanged items.

---

## Phase 6: User Story 4 -- Backward-compatible reading of saved state (P2)

**Goal**: Saved selections and residue tags written with `"merge"` load without error and resolve to LINK.

**Independent Test**: Round-trip a `Selection` with `category_conflict_modes["pos"] = "merge"` through `conflict_mode_for`; result is LINK. A residue tag containing `merge=` (base64 `MergeDecisionLog` encoding) parses without error. (Spec US4 scenarios 1-2.)

- [ ] T018 [US4] Confirm the T004 shim covers the full saved-selection round-trip: write a unit test that constructs a `Selection` dict with `"merge"` values, passes it through the deserialization path, and asserts LINK is returned for each. Verify no KeyError, no AttributeError.
- [ ] T019 [US4] Confirm residue tag compatibility: the `merge=` segment in `residue.py:27,96,179` and `conflict.py:385` is the `MergeDecisionLog` base64 encoding (DISTINCT from `ConflictMode`). Read the residue parsing code; assert it is NOT broken by the ConflictMode rename (these are separate vocabularies). Document the confirmation in a code comment at the shim site (T004).

**Checkpoint**: 100% of "merge" persisted values resolve to LINK; residue parsing unaffected.

---

## Phase 7: User Story 5 -- Re-run recognizes genuinely untouched fields (P2)

**Goal**: On re-run, the prior-run baseline (residue log) enables 3-way field identity so untouched fields auto-SKIP without prompting. First transfer uses 2-way only and makes no "untouched" claim.

**Independent Test**: Transfer item; change nothing in source; re-run; item is SKIP (3-way baseline). Change one source field; re-run; only that field is surfaced. First transfer (no baseline): 2-way only, no "untouched" label. (Spec US5 scenarios 1-3.)

- [ ] T020 [US5] Add 3-way field comparison in `src/gramtrans/Lib/conflict.py`: when a prior-run baseline exists for an item (residue log entry), compare source vs. baseline vs. target. A field that matches both the baseline and the current target is "untouched" -> auto-SKIP that field. A field that diverges from the baseline is "changed since prior run" -> surface for re-evaluation (per 020 R7 pattern: annotate + prompt, not auto-apply).
- [ ] T021 [US5] Implement the baseline read path in `src/gramtrans/Lib/residue.py`: expose a per-item prior-run baseline accessor (read-only) for the disposition comparison in T020. Must not alter the `MergeDecisionLog` base64 wire format (residue.py:27,96,179).
- [ ] T022 [US5] On first transfer (no prior baseline): fall back to 2-way identical-vs-diverged comparison (T015 path). Disposition report must not claim "untouched" for any field; only "identical" or "diverged" are valid labels on a first run.

**Checkpoint**: re-run with unchanged source yields SKIP via 3-way baseline; changed field surfaced; first run uses 2-way only.

---

## Phase 8: Flexicon Version Gate for Phoneme/Environment (P2)

**Goal**: Phoneme and PH_ENVIRONMENT categories auto-promote from SELECTOR-ONLY to Tier A (full field-diff) when the pyflexicon `ITsString.get_String` fix ships, without requiring a code change in GramTrans.

- [ ] T014 [P] Add a flexicon version check in `src/gramtrans/Lib/conflict.py` (or `src/gramtrans/Lib/selection.py` tier map): if the installed `pyflexicon` version is >= the fix release (to be confirmed when the bug is resolved; use a named constant `_FLEXICON_ITSTRING_FIX_VERSION`), promote Phonemes and PH_ENVIRONMENT from Tier C (blocked) to Tier A (real field-diff). Until then, they remain SELECTOR-ONLY with a `blocked_reason` string in the tier map (020 Tier C). Gate the constant with a `# TODO(Ruling-Y): update version when flexicon ITsString fix ships` comment.

**Checkpoint**: Phoneme/Environment remain SELECTOR-ONLY on current pyflexicon; version constant is defined and documented for future auto-promotion.

---

## Phase 9: Test Updates (~45 refs) (P1)

**Goal**: All existing tests updated for the MERGE->LINK rename and new UPDATE/SKIP assertions added.

- [ ] T023 [P] Update `tests/unit/test_conflict_mode_model.py`:
  - line 66: assert `.value == "link"` (was `"merge"`)
  - line 97: assert `ConflictMode.LINK` exists; assert `ConflictMode.MERGE` raises `AttributeError`
  - line 163: assert `allowed_modes_for(MULTI_INSTANCE_CAT)` includes `ConflictMode.UPDATE`
  - line 261: assert shim -- `conflict_mode_for` with persisted `"merge"` returns `ConflictMode.LINK`
- [ ] T024 [P] Update `tests/unit/test_wizard_page_flow.py:423`: assert control shows "Link to existing (no changes)" (not "Merge"); assert UPDATE is offered for a MULTI_INSTANCE page.
- [ ] T025 [P] Sweep remaining ~40 MERGE refs identified in T001 across the test suite and production code; replace each with LINK (model) or UPDATE (where the old MERGE was used as a proxy for "write something"). Classify each hit before changing: rename (most), semantic change (MULTI_INSTANCE default), or shim (one read point only).
- [ ] T026 [P] Add UPDATE semantic unit tests in `tests/unit/test_update_semantic.py` (new file): (a) diverged non-empty source field -> target takes source value; (b) non-empty target + empty source field -> target preserved; (c) OVERWRITE on same pair -> target blanked (destructive contrast SC-003). Use fake handles.
- [ ] T027 [P] Add SKIP disposition unit tests in `tests/unit/test_disposition.py` (new file): (a) all-identical item -> SKIP, no write; (b) unselected item -> IGNORE (not in plan); (c) >=1 diverged field under UPDATE -> UPDATE disposition, not SKIP (SC-004). Use fake handles.
- [ ] T028 [P] Add re-run baseline tests in `tests/unit/test_rerun_baseline.py` (new file): (a) prior baseline + unchanged source -> 3-way SKIP; (b) no prior baseline -> 2-way only, no "untouched" label; (c) source field changed since baseline -> surfaced for re-evaluation (SC-006).
- [ ] T029 [P] Extend `tests/integration/test_conflict_live.py`: UPDATE behavior on Ejagham Mini->Full GT-Test pair (field A diverged takes source; field B target-only preserved); SKIP on all-identical item; OVERWRITE contrast; shim round-trip on a saved selection (SC-002/003/004/005).

---

## Phase 10: Polish & Cross-Cutting

- [ ] T030 [P] Run full unit suite after all rename + semantic changes; record pre/post counts and any regressions. Attach evidence to STATUS.md.
- [ ] T031 [P] Confirm no remaining `ConflictMode.MERGE` or `"merge"` references in `src/gramtrans/Lib/` (except the shim read point at `conflict_mode_for` which maps FROM "merge"). Confirm `MergeResolution` (models.py:201/205) is untouched.
- [ ] T032 [P] Confirm residue wire-format files (`residue.py:27,96,179; conflict.py:385`) are unmodified from their pre-022 state (the `merge=` segment is the MergeDecisionLog encoding, not the ConflictMode vocabulary).
- [ ] T033 Update [STATUS.md](../../STATUS.md) handoff with 022 completion, shim confirmation, and verification evidence (UPDATE semantic test results, SKIP disposition counts, baseline 3-way test results).

---

## Dependencies & Execution Order

- **Setup (T001-T002)** -> **Foundational (T003-T006)** -> all story phases.
- **US1 (T007-T010)** depends on Foundational (enum + shim + allowed_modes_for in place).
- **US2 (T011-T013)** depends on Foundational; can run parallel to US1 (different files: conflict.py / transfer.py vs. selection_wizard.py).
- **US3 (T015-T017)** depends on US2 (disposition requires knowing what a "write" would be).
- **US4 (T018-T019)** depends on T004 (shim); can run parallel to US2/US3.
- **US5 (T020-T022)** depends on US3 (disposition path) and T021 (baseline read).
- **T014 (flexicon gate)** can run parallel to US1-US4 (separate concern; touches tier map only).
- **Test updates (T023-T029)** depend on all implementation tasks; T023-T025 (rename sweep) should run immediately after Foundational to prevent drift.
- **Polish (T030-T033)** last.

## Parallel Opportunities

- T007-T010 (UI rename) || T011-T013 (UPDATE semantic) -- different files.
- T018-T019 (compat shim verification) || T011-T013 -- independent.
- T014 (flexicon gate) || any story task.
- T026 || T027 || T028 -- independent new test files.

## MVP Scope

**Foundational (T003-T006) + US1 (T007-T010) + ~45-ref test sweep (T023-T025)** constitute the minimum shippable slice: the vocabulary is correct, saved state loads without error, and the test suite is green. US2 (UPDATE semantic) and US3 (true SKIP) are required for the feature to deliver its stated value and should be treated as co-MVP.
